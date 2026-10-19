"""Small read-only Kiwoom REST client for a fixed-IP server.

Selected explicitly with STOCK_MINER_AUTH=env. No local keyring or SDK needed.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import requests

KST = timezone(timedelta(hours=9))
BASE = "https://api.kiwoom.com"
READ_APIS = {
    "ka10035": "/api/dostk/rkinfo",
    "ka90009": "/api/dostk/rkinfo",
    "ka10030": "/api/dostk/rkinfo",
    "ka10059": "/api/dostk/stkinfo",
    "ka10081": "/api/dostk/chart",
}


class KiwoomError(RuntimeError):
    pass


class CloudClient:
    def __init__(self, session=None):
        self.appkey = os.environ.get("KIWOOM_APP_KEY", "").strip()
        self.secretkey = os.environ.get("KIWOOM_SECRET_KEY", "").strip()
        if not self.appkey or not self.secretkey:
            raise KiwoomError("서버의 KIWOOM_APP_KEY / KIWOOM_SECRET_KEY 설정이 필요합니다.")
        self.session = session or requests.Session()
        self.token = None
        self.valid_until = datetime.min.replace(tzinfo=KST)

    def _post(self, path, body, headers=None):
        try:
            response = self.session.post(
                BASE + path, json=body,
                headers={"Content-Type": "application/json;charset=UTF-8", **(headers or {})},
                timeout=(10, 30), allow_redirects=False,
            )
        except requests.RequestException:
            raise KiwoomError("키움 통신 실패. 서버 네트워크를 확인하세요.") from None
        return response

    @staticmethod
    def _body(response):
        if response.status_code != 200:
            raise KiwoomError(f"키움 HTTP 오류 ({response.status_code})")
        try:
            body = response.json()
        except ValueError:
            raise KiwoomError("키움 JSON 응답 형식 오류") from None
        if not isinstance(body, dict):
            raise KiwoomError("키움 응답이 객체가 아닙니다.")
        return body

    def _login(self):
        body = self._body(self._post("/oauth2/token", {
            "grant_type": "client_credentials", "appkey": self.appkey,
            "secretkey": self.secretkey,
        }))
        if str(body.get("return_code")) != "0" or not body.get("token"):
            # Do not log raw responses, credentials or access tokens.
            raise KiwoomError("키움 인증 실패. 앱키와 서버의 허용 IP 등록을 확인하세요.")
        try:
            expiry = datetime.strptime(body["expires_dt"], "%Y%m%d%H%M%S").replace(tzinfo=KST)
        except (KeyError, ValueError, TypeError):
            raise KiwoomError("키움 토큰 만료시각 누락 또는 형식 오류") from None
        if expiry <= datetime.now(KST):
            raise KiwoomError("이미 만료된 키움 토큰입니다.")
        self.token = body["token"]
        self.valid_until = expiry - timedelta(minutes=2)

    def fetch_page(self, *, api_id, path, body, cont_yn=None, next_key=None):
        if READ_APIS.get(api_id) != path:
            raise KiwoomError("Stock Miner 조회용 API만 허용됩니다.")
        for attempt in range(2):
            if not self.token or datetime.now(KST) >= self.valid_until:
                self._login()
            headers = {"authorization": "Bearer " + self.token, "api-id": api_id}
            if cont_yn:
                headers["cont-yn"] = cont_yn
            if next_key:
                headers["next-key"] = next_key
            response = self._post(path, body, headers)
            if response.status_code == 401 and attempt == 0:
                self.token = None
                continue
            payload = self._body(response)
            if str(payload.get("return_code", 0)) != "0":
                raise KiwoomError(f"키움 조회 실패 ({api_id}). 응답 상태를 확인하세요.")
            return SimpleNamespace(body=payload, continuation=SimpleNamespace(
                cont_yn=response.headers.get("cont-yn"),
                next_key=response.headers.get("next-key"),
            ))
        raise KiwoomError("키움 인증 재시도 실패")


_client = None


def get_client():
    global _client
    if _client is None:
        _client = CloudClient()
    return _client
