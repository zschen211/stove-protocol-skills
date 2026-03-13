'''
写一个爬虫脚本，将以下网站的 html 内容全部爬下来
 1. https://docs.proto.stove.finance/public
 2. https://docs.proto.stove.finance/taker
 3. https://docs.proto.stove.finance/maker

 将爬下来的 html 内容保存到本地，文件名称为网站的 url 的 md5 值。创建三个文件夹，分别用于保存三个网站的 html 内容。

 使用 python 的 requests 库和 BeautifulSoup 库来实现。
 使用 python 的 threading 库来实现多线程爬取。
 使用 python 的 logging 库来实现日志记录。
 使用 python 的 argparse 库来实现命令行参数解析。
'''

import argparse
import hashlib
import logging
import os
import queue
import threading
from dataclasses import dataclass
from typing import Set
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup


BASE_URLS = [
    'https://docs.proto.stove.finance/public',
    'https://docs.proto.stove.finance/taker',
    'https://docs.proto.stove.finance/maker',
]


@dataclass
class CrawlerConfig:
    base_url: str
    output_dir: str
    workers: int = 8
    timeout: int = 15


class SiteCrawler:
    def __init__(self, config: CrawlerConfig) -> None:
        self.config = config
        self.queue: 'queue.Queue[str]' = queue.Queue()
        self.visited: Set[str] = set()
        self.visited_lock = threading.Lock()
        self.session = requests.Session()

        parsed = urlparse(config.base_url)
        # 只在同一域名且在该基准路径下爬取
        self.domain = parsed.netloc
        self.base_path = parsed.path.rstrip('/') or '/'

        os.makedirs(config.output_dir, exist_ok=True)

    def start(self) -> None:
        logging.info('开始爬取站点: %s', self.config.base_url)
        self.queue.put(self.config.base_url)

        threads = []
        for i in range(self.config.workers):
            t = threading.Thread(target=self.worker, name=f'worker-{i+1}', daemon=True)
            threads.append(t)
            t.start()

        # 等待队列任务完成
        self.queue.join()

        logging.info('站点爬取完成: %s, 共抓取页面: %d', self.config.base_url, len(self.visited))

    def worker(self) -> None:
        while True:
            try:
                url = self.queue.get(timeout=2)
            except queue.Empty:
                # 队列暂时为空且没有待处理任务时退出
                if self.queue.empty():
                    return
                continue

            try:
                self.crawl_page(url)
            except Exception as exc:  # noqa: BLE001
                logging.exception('抓取页面出错: %s, error=%s', url, exc)
            finally:
                self.queue.task_done()

    def crawl_page(self, url: str) -> None:
        with self.visited_lock:
            if url in self.visited:
                return
            self.visited.add(url)

        logging.info('抓取页面: %s', url)
        headers = {
            'User-Agent': 'stove-protocol-crawler/1.0 (+https://docs.proto.stove.finance/)',
        }
        resp = self.session.get(url, headers=headers, timeout=self.config.timeout)

        if resp.status_code != 200:
            logging.warning('抓取失败: %s, status=%s', url, resp.status_code)
            return

        html = resp.text
        self.save_html(url, html)
        self.enqueue_links(url, html)

    def save_html(self, url: str, html: str) -> None:
        """保存精简版 HTML，只保留文档主体内容。"""
        cleaned_html = self._extract_main_content(html)

        md5_name = hashlib.md5(url.encode('utf-8')).hexdigest()  # noqa: S324
        file_path = os.path.join(self.config.output_dir, f'{md5_name}.html')
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(cleaned_html)
            logging.debug('保存页面: %s -> %s', url, file_path)
        except OSError as exc:
            logging.error('保存页面失败: %s, error=%s', url, exc)

    def _extract_main_content(self, html: str) -> str:
        """提取 Stove 文档站点的正文区域，去掉导航、脚本等冗余内容。

        - 优先查找 class 中包含 'vp-doc' 的 div（正文容器）
        - 退化处理：找不到时返回原始 HTML，避免误删内容
        """
        try:
            soup = BeautifulSoup(html, 'html.parser')

            # 找标题，方便放到 <title> 里
            title_tag = soup.find('title')
            title = title_tag.get_text(strip=True) if title_tag else ''

            # VitePress 默认正文容器：div.vp-doc 或包含 vp-doc 的类名
            main_div = None
            for div in soup.find_all('div'):
                classes = div.get('class') or []
                if any('vp-doc' == c or c.startswith('vp-doc') or c.endswith('vp-doc') for c in classes):
                    main_div = div
                    break

            if main_div is None:
                # 兜底：尝试 main.main
                main = soup.find('main')
                if main is not None:
                    main_div = main

            if main_div is None:
                logging.debug('未找到正文容器，保存原始 HTML')
                return html

            # 生成一个极简 HTML 文档，只保留必要结构
            doc = BeautifulSoup('<!DOCTYPE html><html><head></head><body></body></html>', 'html.parser')
            head = doc.find('head')
            body = doc.find('body')

            meta = doc.new_tag('meta', charset='utf-8')
            head.append(meta)

            if title:
                t = doc.new_tag('title')
                t.string = title
                head.append(t)

            body.append(main_div)

            return str(doc)
        except Exception as exc:  # noqa: BLE001
            logging.exception('提取正文失败，回退到原始 HTML: %s', exc)
            return html

    def enqueue_links(self, current_url: str, html: str) -> None:
        soup = BeautifulSoup(html, 'html.parser')
        for a in soup.find_all('a', href=True):
            href = a['href'].strip()
            if not href or href.startswith('#'):
                continue

            next_url = urljoin(current_url, href)
            parsed = urlparse(next_url)

            if parsed.scheme not in ('http', 'https'):
                continue

            if parsed.netloc != self.domain:
                continue

            path = parsed.path or '/'
            if not path.startswith(self.base_path):
                continue

            normalized = parsed._replace(fragment='').geturl()
            with self.visited_lock:
                if normalized in self.visited:
                    continue
            # 可能被其他线程加入 visited，因此这里不再检查重复，只依赖 visited 锁
            self.queue.put(normalized)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='多线程爬取 Stove Protocol 文档站点 HTML 内容到本地。',
    )
    parser.add_argument(
        '--output-dir',
        default='output',
        help='保存所有站点 HTML 的根目录（默认: %(default)s）',
    )
    parser.add_argument(
        '--workers',
        type=int,
        default=8,
        help='每个站点的爬取线程数（默认: %(default)s）',
    )
    parser.add_argument(
        '--log-level',
        default='INFO',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
        help='日志级别（默认: %(default)s）',
    )
    return parser.parse_args()


def setup_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format='[%(asctime)s] [%(levelname)s] [%(threadName)s] %(message)s',
    )


def main() -> None:
    args = parse_args()
    setup_logging(args.log_level)

    for base_url in BASE_URLS:
        # 以最后一段路径名作为子目录名，例如 public/taker/maker
        tail = urlparse(base_url).path.rstrip('/').split('/')[-1] or 'root'
        site_output_dir = os.path.join(args.output_dir, tail)

        config = CrawlerConfig(
            base_url=base_url,
            output_dir=site_output_dir,
            workers=max(1, int(args.workers)),
        )
        crawler = SiteCrawler(config)
        crawler.start()


if __name__ == '__main__':
    main()

