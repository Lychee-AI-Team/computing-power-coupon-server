import base64
import json
import os
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.serialization import load_pem_private_key, load_pem_public_key
from fastapi import HTTPException, status

from app.core.config import settings


@dataclass
class WechatPayConfig:
    appid: str
    mch_id: str
    api_v3_key: str
    private_key: str
    mch_serial_no: str
    public_key: str
    notify_url: str


def _get_config(for_payment: bool = True) -> WechatPayConfig:
    cfg = WechatPayConfig(
        appid=settings.WECHAT_APPID,
        mch_id=settings.WECHAT_MCH_ID,
        api_v3_key=settings.WECHAT_API_V3_KEY,
        private_key=settings.WECHAT_PRIVATE_KEY,
        mch_serial_no=settings.WECHAT_MCH_SERIAL_NO,
        public_key=settings.WECHAT_PUBLIC_KEY,
        notify_url=settings.WECHAT_NOTIFY_URL,
    )
    if for_payment:
        if not all([cfg.appid, cfg.mch_id, cfg.api_v3_key, cfg.private_key,
                    cfg.mch_serial_no, cfg.notify_url]):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="WeChat Pay is not configured",
            )
    return cfg


_NATIVE_URL = "https://api.mch.weixin.qq.com/v3/pay/transactions/native"
_CLOSE_URL = "https://api.mch.weixin.qq.com/v3/pay/transactions/out-trade-no/{out_trade_no}/close"


class WechatPayService:
    def __init__(self, client: httpx.AsyncClient):
        self.client = client

    async def create_native_payment(
        self, order_no: str, total_fee: int, body: str,
    ) -> dict[str, Any]:
        cfg = _get_config()
        req_body = {
            "appid": cfg.appid,
            "mchid": cfg.mch_id,
            "description": body,
            "out_trade_no": order_no,
            "notify_url": cfg.notify_url,
            "amount": {
                "total": total_fee,
                "currency": "CNY",
            },
        }
        body_bytes = json.dumps(req_body, ensure_ascii=False).encode()

        headers = _build_v3_headers(
            cfg.mch_id, cfg.mch_serial_no, cfg.private_key,
            "POST", _NATIVE_URL, body_bytes,
        )
        headers["Content-Type"] = "application/json"
        headers["Accept"] = "application/json"

        resp = await self.client.post(_NATIVE_URL, content=body_bytes, headers=headers)
        if resp.status_code != 200:
            self._handle_api_error(resp)
        result = resp.json()
        return {"code_url": result["code_url"], "order_no": order_no}

    async def close_order(self, order_no: str) -> None:
        """关闭微信支付订单，使二维码失效."""
        cfg = _get_config(for_payment=False)
        if not all([cfg.appid, cfg.mch_id, cfg.api_v3_key, cfg.private_key, cfg.mch_serial_no]):
            return
        url = _CLOSE_URL.format(out_trade_no=order_no)
        req_body = {"mchid": cfg.mch_id}
        body_bytes = json.dumps(req_body, ensure_ascii=False).encode()
        headers = _build_v3_headers(
            cfg.mch_id, cfg.mch_serial_no, cfg.private_key,
            "POST", url, body_bytes,
        )
        headers["Content-Type"] = "application/json"
        headers["Accept"] = "application/json"
        resp = await self.client.post(url, content=body_bytes, headers=headers)
        if resp.status_code not in (200, 204):
            self._handle_api_error(resp)

    @staticmethod
    def verify_notify_sign(
        body: bytes, wechatpay_signature: str, wechatpay_timestamp: str,
        wechatpay_nonce: str, wechatpay_serial: str,
    ) -> dict[str, Any] | None:
        cfg = _get_config(for_payment=False)
        if not cfg.public_key or not cfg.api_v3_key:
            return None

        message = f"{wechatpay_timestamp}\n{wechatpay_nonce}\n{body.decode()}\n"
        if not _verify_rsa_sign(cfg.public_key, message, wechatpay_signature):
            return None

        data = json.loads(body.decode())
        resource = data.get("resource", {})
        ciphertext = resource.get("ciphertext", "")
        nonce = resource.get("nonce", "")
        associated_data = resource.get("associated_data", "")

        decrypted = _aes_gcm_decrypt(cfg.api_v3_key, nonce, ciphertext, associated_data)
        if decrypted is None:
            return None
        return json.loads(decrypted)

    @staticmethod
    def build_notify_reply() -> dict[str, Any]:
        return {"code": "SUCCESS", "message": "OK"}

    @staticmethod
    def _handle_api_error(resp: httpx.Response) -> None:
        try:
            err = resp.json()
            detail = err.get("message", "WeChat Pay error")
        except Exception:
            detail = resp.text or "WeChat Pay error"
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=detail)


def _build_v3_headers(
    mch_id: str, serial_no: str, private_key_pem: str,
    method: str, url: str, body: bytes,
) -> dict[str, str]:
    nonce_str = uuid.uuid4().hex[:32]
    timestamp = str(int(datetime.now().timestamp()))
    path = url.replace("https://api.mch.weixin.qq.com", "")
    message = f"{method}\n{path}\n{timestamp}\n{nonce_str}\n{body.decode()}\n"
    signature = _make_rsa_sign(private_key_pem, message)
    auth = (
        f'WECHATPAY2-SHA256-RSA2048 mchid="{mch_id}",'
        f'nonce_str="{nonce_str}",'
        f'timestamp="{timestamp}",'
        f'serial_no="{serial_no}",'
        f'signature="{signature}"'
    )
    return {"Authorization": auth}


def _resolve_key(value: str) -> str:
    """如果 value 是文件路径则读取文件内容，否则直接返回"""
    path = Path(value)
    if path.suffix in (".pem", ".key", ".crt") and path.exists():
        return path.read_text()
    # 尝试作为相对路径解析
    alt = Path(os.getcwd()) / value
    if Path(value).suffix in (".pem", ".key", ".crt") and alt.exists():
        return alt.read_text()
    return value


def _make_rsa_sign(private_key_val: str, message: str) -> str:
    try:
        key_pem = _resolve_key(private_key_val)
        key = load_pem_private_key(key_pem.encode(), password=None)
        signature = key.sign(message.encode(), padding.PKCS1v15(), hashes.SHA256())
        return base64.b64encode(signature).decode()
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Invalid WeChat Pay private key",
        )


def _verify_rsa_sign(public_key_val: str, message: str, signature: str) -> bool:
    try:
        key_pem = _resolve_key(public_key_val)
        key = load_pem_public_key(key_pem.encode())
        key.verify(
            base64.b64decode(signature),
            message.encode(),
            padding.PKCS1v15(),
            hashes.SHA256(),
        )
        return True
    except Exception:
        return False


def _aes_gcm_decrypt(
    api_v3_key: str, nonce: str, ciphertext: str, associated_data: str,
) -> str | None:
    try:
        key = api_v3_key.encode()
        aesgcm = AESGCM(key)
        decrypted = aesgcm.decrypt(
            nonce.encode(),
            base64.b64decode(ciphertext),
            associated_data.encode(),
        )
        return decrypted.decode()
    except Exception:
        return None