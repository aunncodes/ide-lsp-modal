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
        self._jdtls_real_uri: str | None = None
        self._jdtls_client_uri = "file:///workspace/main.java"

    async def aenter(self) -> str:
        self._jdtls_data = tempfile.TemporaryDirectory(prefix="jdtls-data-")
        project_file = os.path.join(self._jdtls_data.name, ".project")
        with open(project_file, "w") as f:
            f.write(PROJECT_XML)
        main_path = os.path.join(self._jdtls_data.name, "Main.java")
        open(main_path, "w").close()

        self._jdtls_real_uri = pathlib.Path(main_path).absolute().as_uri()

        return self._command + f" -data {self._jdtls_data.name}"

    async def aexit(self) -> None:
        self._jdtls_data.cleanup()

    async def ws_to_lsp(self, data: str) -> str:
        obj = json.loads(data)

        if obj.get("method") == "initialize":
            params = obj["params"]
            workspace_uri = pathlib.Path(self._jdtls_data.name).absolute().as_uri()
            params["rootUri"] = workspace_uri
            params["workspaceFolders"] = [{"uri": workspace_uri, "name": "workspace"}]

        if self._jdtls_real_uri:
            return json.dumps(obj).replace(self._jdtls_client_uri, self._jdtls_real_uri)

        return json.dumps(obj)

    async def lsp_to_ws(self, data: str) -> str:
        if self._jdtls_real_uri:
            return data.replace(self._jdtls_real_uri, self._jdtls_client_uri)
        return data
