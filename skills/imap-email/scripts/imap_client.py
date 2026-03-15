"""
IMAP 客户端脚本：列出文件夹、列出邮件摘要、获取单封邮件内容。
仅使用 Python 标准库 imaplib、email。
"""
import argparse
import email
import imaplib
import json
import os
import sys
from dataclasses import dataclass
from email import policy
from typing import Any, Dict, List, Optional


@dataclass
class ImapConfig:
    host: str
    port: int
    user: str
    password: str
    use_ssl: bool


def get_config(args: argparse.Namespace) -> ImapConfig:
    password = os.environ.get("IMAP_PASSWORD")
    if not password:
        raise SystemExit(
            "未设置 IMAP_PASSWORD 环境变量。请在执行前 export IMAP_PASSWORD='...' 或在 OpenClaw 中配置 imap_password。"
        )
    return ImapConfig(
        host=args.host,
        port=args.port,
        user=args.user,
        password=password,
        use_ssl=args.use_ssl,
    )


def connect(cfg: ImapConfig) -> imaplib.IMAP4:
    if cfg.use_ssl:
        conn = imaplib.IMAP4_SSL(cfg.host, cfg.port)
    else:
        conn = imaplib.IMAP4(cfg.host, cfg.port)
    conn.login(cfg.user, cfg.password)
    return conn


def _decode_header(s: Optional[str]) -> str:
    if s is None:
        return ""
    if isinstance(s, bytes):
        return s.decode("utf-8", errors="replace")
    return str(s)


def _parse_address(addr: Any) -> str:
    if addr is None:
        return ""
    if isinstance(addr, (list, tuple)):
        parts = []
        for a in addr:
            if isinstance(a, (list, tuple)) and len(a) >= 2:
                # (name, email) or (email,) 
                email_addr = a[-1]
                if isinstance(email_addr, bytes):
                    email_addr = email_addr.decode("utf-8", errors="replace")
                parts.append(email_addr)
            elif isinstance(a, bytes):
                parts.append(a.decode("utf-8", errors="replace"))
            elif isinstance(a, str):
                parts.append(a)
        return ", ".join(parts)
    if isinstance(addr, bytes):
        return addr.decode("utf-8", errors="replace")
    return str(addr)


def cmd_list_folders(cfg: ImapConfig, _args: argparse.Namespace) -> None:
    conn = connect(cfg)
    try:
        status, data = conn.list()
        if status != "OK":
            out = {"error": "LIST failed", "status": status}
            json.dump(out, sys.stdout, ensure_ascii=False, indent=2)
            return
        folders: List[str] = []
        for item in data or []:
            if isinstance(item, bytes):
                item = item.decode("utf-8", errors="replace")
            # 格式通常为: (\HasNoChildren) "." "INBOX"
            parts = item.split(' "')
            if len(parts) >= 2:
                name = parts[-1].rstrip('"').strip()
                if name:
                    folders.append(name)
        json.dump({"folders": folders}, sys.stdout, ensure_ascii=False, indent=2)
    finally:
        conn.logout()
    sys.stdout.write("\n")


def cmd_list_mails(cfg: ImapConfig, args: argparse.Namespace) -> None:
    folder = args.folder or "INBOX"
    limit = max(1, min(100, args.limit or 10))
    conn = connect(cfg)
    try:
        status, _ = conn.select(folder, readonly=True)
        if status != "OK":
            json.dump(
                {"error": f"SELECT {folder} failed", "status": status},
                sys.stdout,
                ensure_ascii=False,
                indent=2,
            )
            sys.stdout.write("\n")
            return
        status, data = conn.uid("SEARCH", None, "ALL")
        if status != "OK" or not data or not data[0].strip():
            json.dump({"mails": [], "folder": folder}, sys.stdout, ensure_ascii=False, indent=2)
            sys.stdout.write("\n")
            return
        uids = data[0].split()
        uids = uids[-limit:][::-1]
        mails: List[Dict[str, Any]] = []
        for uid_bytes in uids:
            uid = uid_bytes.decode("utf-8", errors="replace") if isinstance(uid_bytes, bytes) else str(uid_bytes)
            status, hdata = conn.uid("FETCH", uid_bytes, "(BODY.PEEK[HEADER.FIELDS (DATE FROM SUBJECT)])")
            if status != "OK" or not hdata or not hdata[0]:
                mails.append({"uid": uid, "subject": "", "from": "", "date": ""})
                continue
            raw = hdata[0]
            if isinstance(raw, tuple) and len(raw) >= 2 and isinstance(raw[1], bytes):
                msg = email.message_from_bytes(b"Header: value\r\n\r\n" + raw[1], policy=policy.default)
            else:
                msg = None
            subject = _decode_header(msg.get("Subject", "")) if msg else ""
            from_ = _decode_header(msg.get("From", "")) if msg else ""
            date = _decode_header(msg.get("Date", "")) if msg else ""
            mails.append({"uid": uid, "subject": subject, "from": from_, "date": date})
        json.dump({"folder": folder, "mails": mails}, sys.stdout, ensure_ascii=False, indent=2)
    finally:
        conn.logout()
    sys.stdout.write("\n")


def _get_text_body(msg: email.message.Message) -> str:
    text_parts: List[str] = []
    for part in msg.walk():
        ctype = part.get_content_type()
        if ctype == "text/plain":
            payload = part.get_payload(decode=True)
            if payload:
                charset = part.get_content_charset() or "utf-8"
                try:
                    text_parts.append(payload.decode(charset, errors="replace"))
                except Exception:
                    text_parts.append(payload.decode("utf-8", errors="replace"))
        elif ctype == "text/html" and not text_parts:
            payload = part.get_payload(decode=True)
            if payload:
                charset = part.get_content_charset() or "utf-8"
                try:
                    raw = payload.decode(charset, errors="replace")
                except Exception:
                    raw = payload.decode("utf-8", errors="replace")
                # 简单 strip 标签，只保留可见文本的大致内容
                import re
                raw = re.sub(r"<[^>]+>", " ", raw)
                raw = re.sub(r"\s+", " ", raw).strip()
                text_parts.append(raw[:8000])
    return "\n".join(text_parts) if text_parts else ""


def cmd_get_mail(cfg: ImapConfig, args: argparse.Namespace) -> None:
    folder = args.folder or "INBOX"
    uid = args.uid
    if not uid:
        raise SystemExit("get-mail 需要 --uid 参数（邮件 UID，可从 list-mails 输出中获取）。")
    conn = connect(cfg)
    try:
        status, _ = conn.select(folder, readonly=True)
        if status != "OK":
            json.dump(
                {"error": f"SELECT {folder} failed", "status": status},
                sys.stdout,
                ensure_ascii=False,
                indent=2,
            )
            sys.stdout.write("\n")
            return
        status, data = conn.uid("FETCH", uid, "(RFC822)")
        if status != "OK" or not data or not data[0]:
            json.dump(
                {"error": "FETCH failed", "uid": uid, "status": status},
                sys.stdout,
                ensure_ascii=False,
                indent=2,
            )
            sys.stdout.write("\n")
            return
        part = data[0]
        if not isinstance(part, tuple) or len(part) < 2:
            json.dump({"error": "No message body", "uid": uid}, sys.stdout, ensure_ascii=False, indent=2)
            sys.stdout.write("\n")
            return
        raw = part[1]
        if isinstance(raw, bytes):
            msg = email.message_from_bytes(raw, policy=policy.default)
        else:
            json.dump({"error": "Invalid message", "uid": uid}, sys.stdout, ensure_ascii=False, indent=2)
            sys.stdout.write("\n")
            return
        subject = _decode_header(msg.get("Subject", ""))
        from_ = _decode_header(msg.get("From", ""))
        to_ = _decode_header(msg.get("To", ""))
        date = _decode_header(msg.get("Date", ""))
        body = _get_text_body(msg)
        out = {
            "uid": uid,
            "folder": folder,
            "subject": subject,
            "from": from_,
            "to": to_,
            "date": date,
            "body": body[:50000],
        }
        json.dump(out, sys.stdout, ensure_ascii=False, indent=2)
    finally:
        conn.logout()
    sys.stdout.write("\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="IMAP 客户端：列出文件夹、列出邮件、查看单封邮件。密码请通过环境变量 IMAP_PASSWORD 设置。",
    )
    parser.add_argument("--host", required=True, help="IMAP 服务器地址。")
    parser.add_argument("--port", type=int, default=993, help="IMAP 端口，默认 993。")
    parser.add_argument("--user", required=True, help="登录用户名/邮箱。")
    parser.add_argument("--no-ssl", action="store_true", help="不使用 SSL（如端口 143）。")
    parser.add_argument("--folder", default="INBOX", help="邮箱文件夹，默认 INBOX。")

    subparsers = parser.add_subparsers(dest="command", required=True)

    p_list_folders = subparsers.add_parser("list-folders", help="列出所有文件夹。")
    p_list_folders.set_defaults(func=cmd_list_folders)

    p_list_mails = subparsers.add_parser("list-mails", help="列出指定文件夹中的近期邮件摘要。")
    p_list_mails.add_argument("--folder", default="INBOX", help="文件夹名，默认 INBOX。")
    p_list_mails.add_argument("--limit", type=int, default=10, help="最多列出几封，默认 10。")
    p_list_mails.set_defaults(func=cmd_list_mails)

    p_get = subparsers.add_parser("get-mail", help="根据 UID 获取单封邮件全文。")
    p_get.add_argument("--folder", default="INBOX", help="文件夹名，默认 INBOX。")
    p_get.add_argument("--uid", required=True, help="邮件 UID（从 list-mails 输出中获取）。")
    p_get.set_defaults(func=cmd_get_mail)

    args = parser.parse_args()
    args.use_ssl = not getattr(args, "no_ssl", False)
    cfg = get_config(args)
    args.func(cfg, args)


if __name__ == "__main__":
    main()
