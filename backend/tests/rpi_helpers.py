import io
import re
import zipfile
from pathlib import Path

import httpx

from app.rpi import http as rpi_http

FIX = Path(__file__).parent / "fixtures"


def xml_text(numero: int = 2914, extra: str = "") -> str:
    xml = (FIX / "RM2914.xml").read_text(encoding="utf-8")
    xml = xml.replace('<revista numero="2914"', f'<revista numero="{numero}"')
    if extra:
        xml = xml.replace("</revista>", extra + "\n</revista>")
    return xml


def make_zip(xml: str, name: str = "RM2914.xml") -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(name, xml.encode("utf-8"))
    return buf.getvalue()


class FakeINPI:
    """Simula revistas.inpi.gov.br."""

    def __init__(self):
        self.index = (FIX / "rpi_index.html").read_text(encoding="utf-8")
        self.files: dict[str, bytes] = {
            "RM2914.zip": make_zip(xml_text(2914)),
            "RM2913.zip": make_zip(xml_text(2913), "RM2913.xml"),
        }
        self.status: dict[str, int] = {}
        self.calls: list[str] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        self.calls.append(url)
        if url.endswith("/rpi/"):
            return httpx.Response(200, text=self.index)
        name = url.rsplit("/", 1)[-1]
        if self.status.get(name):
            return httpx.Response(self.status[name])
        if name in self.files:
            return httpx.Response(200, content=self.files[name])
        if re.match(r"Marcas\d+_[IV]+\.pdf", name):
            return httpx.Response(200, content=b"%PDF-1.4 fake " + name.encode())
        return httpx.Response(404)

    def install(self):
        rpi_http.transport = httpx.MockTransport(self.handler)
        return self
