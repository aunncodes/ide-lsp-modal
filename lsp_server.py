import pathlib
from fastapi import FastAPI, WebSocket
from modal import Image, App, asgi_app
import modal
from adapters.clangd import ClangdAdapter
from adapters.default import DefaultAdapter
from adapters.jdtls import JdtlsAdapter
from lsp_process import LanguageServerProcess

main_web_app = FastAPI()
jdtls_web_app = FastAPI()

ROOT = pathlib.Path(__file__).parent

app = App("lsp-server")

image = (
    Image.debian_slim()
    .apt_install("wget", "unzip", "tar")
    .pip_install("fastapi[standard]")
    .run_commands(
        "wget -nv https://nodejs.org/dist/v20.14.0/node-v20.14.0-linux-x64.tar.xz",
        "tar -xf node-v20.14.0-linux-x64.tar.xz",
        "rm node-v20.14.0-linux-x64.tar.xz",
        *[
            f"ln -s /node-v20.14.0-linux-x64/bin/{binary} /bin/{binary}"
            for binary in ("node", "npm")
        ],
        "npm install -g pyright",
    )
    .run_commands(
        "wget -nv https://github.com/clangd/clangd/releases/download/18.1.3/clangd-linux-18.1.3.zip",
        "unzip -q clangd-linux-18.1.3.zip",
        "rm clangd-linux-18.1.3.zip",
        # Note: clangd requires $(dirname $(which clangd))/../lib/clang to exist
        "mv clangd_18.1.3/bin/clangd /usr/bin",
        "mv clangd_18.1.3/lib/clang /usr/lib/clang",
    )
    .run_commands(
        "mkdir -p /opt/java",
        "wget -nv https://github.com/adoptium/temurin21-binaries/releases/download/jdk-21.0.10%2B7/OpenJDK21U-jdk_x64_linux_hotspot_21.0.10_7.tar.gz -O /tmp/jdk21.tar.gz",
        "tar -xzf /tmp/jdk21.tar.gz -C /opt/java",
        "rm /tmp/jdk21.tar.gz",
        "ln -sf /opt/java/jdk-21*/bin/java /usr/local/bin/java",
        "ln -sf /opt/java/jdk-21*/bin/javac /usr/local/bin/javac",
        "mkdir -p /opt/jdtls",
        "wget -nv https://download.eclipse.org/jdtls/snapshots/jdt-language-server-latest.tar.gz -O /tmp/jdtls.tar.gz",
        "tar -xzf /tmp/jdtls.tar.gz -C /opt/jdtls",
        "rm /tmp/jdtls.tar.gz",
    )
    .add_local_dir(
        ROOT.as_posix(),
        remote_path="/root"
    )
)

PYTHON_LANGSERVER = "/node-v20.14.0-linux-x64/bin/pyright-langserver --stdio"
CLANGD_LANGSERVER = "clangd --log=error --background-index=false --malloc-trim"
JDTLS_BASE = (
    "/usr/local/bin/java "
    "-Declipse.application=org.eclipse.jdt.ls.core.id1 "
    "-Dosgi.bundles.defaultStartLevel=4 "
    "-Declipse.product=org.eclipse.jdt.ls.core.product "
    "-Dlog.protocol=true "
    "-Dlog.level=error "
    "-Xms256m -Xmx1g "
    "-jar /opt/jdtls/plugins/org.eclipse.equinox.launcher_*.jar "
    "-configuration /opt/jdtls/config_linux"
)


@main_web_app.websocket("/pyright")
async def pyright_endpoint(websocket: WebSocket):
    await websocket.accept()

    async with LanguageServerProcess(DefaultAdapter(PYTHON_LANGSERVER)) as lsp:
        # read first two initialization messages
        for _ in range(2):
            await lsp.read_msg()

        print("Got pyright connection!")
        await lsp.connect_ws(websocket)
        print("Pyright websocket disconnected, stopping language server")


@main_web_app.websocket("/clangd")
async def clangd_endpoint(websocket: WebSocket, compiler_options: str | None = None):
    await websocket.accept()

    async with LanguageServerProcess(
        ClangdAdapter(CLANGD_LANGSERVER, compiler_options=compiler_options)
    ) as lsp:
        print(f"Got clangd connection with options `{compiler_options}`")
        await lsp.connect_ws(websocket)
        print("Clangd websocket disconnected, stopping language server")


@jdtls_web_app.websocket("/jdtls")
async def jdtls_endpoint(websocket: WebSocket):
    await websocket.accept()
    async with LanguageServerProcess(JdtlsAdapter(JDTLS_BASE)) as lsp:
        print("Got jdtls connection!")
        await lsp.connect_ws(websocket)
        print("JDTLS websocket disconnected, stopping language server")


@app.function(
    image=image,
    timeout=60 * 60,
)
@modal.concurrent(max_inputs=20)
@asgi_app()
def main():
    return main_web_app


@app.function(
    image=image,
    timeout=60 * 60,
)
@modal.concurrent(max_inputs=3)
@asgi_app()
def jdtls():
    return jdtls_web_app
