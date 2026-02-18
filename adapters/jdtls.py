import json
import os
import pathlib
import tempfile
from .base import LanguageServerAdapter
from jdtls_templates import PROJECT_XML


class JdtlsAdapter(LanguageServerAdapter):
    def __init__(self, command: str):
        self._command = command
        self._jdtls_data: tempfile.TemporaryDirectory | None = None
        self._jdtls_project: tempfile.TemporaryDirectory | None = None
        self._jdtls_main_path: str | None = None
        self._jdtls_real_uri: str | None = None
        self._jdtls_client_uri = "file:///workspace/main.java"

    async def aenter(self) -> str:
        self._jdtls_data = tempfile.TemporaryDirectory(prefix="jdtls-data-")
        self._jdtls_project = tempfile.TemporaryDirectory(prefix="jdtls-project-")
        project_file = os.path.join(self._jdtls_project.name, ".project")
        with open(project_file, "w", encoding="utf-8") as f:
            f.write(PROJECT_XML)

        self._jdtls_main_path = os.path.join(self._jdtls_project.name, "Main.java")
        open(self._jdtls_main_path, "w", encoding="utf-8").close()

        self._jdtls_real_uri = pathlib.Path(self._jdtls_main_path).absolute().as_uri()

        return self._command + f" -data {self._jdtls_data.name}"

    async def aexit(self) -> None:
        if self._jdtls_project is not None:
            self._jdtls_project.cleanup()
        if self._jdtls_data is not None:
            self._jdtls_data.cleanup()

    async def ws_to_lsp(self, data: str) -> str:
        obj = json.loads(data)
        method = obj.get("method")

        if method == "initialize":
            params = obj["params"]
            params["rootUri"] = pathlib.Path(self._jdtls_project.name).absolute().as_uri()
            params["workspaceFolders"] = [
                {"uri": pathlib.Path(self._jdtls_project.name).absolute().as_uri(), "name": "workspace"}
            ]

        if self._jdtls_real_uri:
            data = json.dumps(obj).replace(self._jdtls_client_uri, self._jdtls_real_uri)
            obj = json.loads(data)

        if self._jdtls_main_path:
            if method == "textDocument/didOpen":
                text = obj["params"]["textDocument"]["text"]
                with open(self._jdtls_main_path, "w", encoding="utf-8") as f:
                    f.write(text)

            elif method == "textDocument/didChange":
                text = obj["params"]["contentChanges"][-1]["text"]
                with open(self._jdtls_main_path, "w", encoding="utf-8") as f:
                    f.write(text)

        return json.dumps(obj)

    async def lsp_to_ws(self, data: str) -> str:
        if self._jdtls_real_uri:
            return data.replace(self._jdtls_real_uri, self._jdtls_client_uri)
        return data
