"""requirements.lock.txt pins every server package, matches what the tests run with, and Docker uses it."""
import re
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _norm(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def lock() -> dict[str, str]:
    pins = {}
    for line in (ROOT / "requirements.lock.txt").read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.startswith("#"):
            name, sep, ver = line.partition("==")
            assert sep and ver, f"not an exact pin: {line}"
            pins[_norm(name)] = ver.strip()
    return pins


def test_every_server_package_is_pinned():
    wanted = [_norm(re.split(r"[\[<>=;\s]", l)[0]) for l in (ROOT / "requirements.txt").read_text().splitlines()
              if l.strip() and not l.startswith("#")]
    pins = lock()
    assert all(w in pins for w in wanted), [w for w in wanted if w not in pins]


def test_installed_versions_match_the_lock():
    """The tests run with exactly the versions the server will get."""
    wrong = []
    for name, ver in lock().items():
        try:
            if version(name) != ver:
                wrong.append(f"{name}: installed {version(name)}, locked {ver}")
        except PackageNotFoundError:
            wrong.append(f"{name}: not installed")
    assert wrong == []


def test_docker_installs_from_the_lock():
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "pip install --no-cache-dir -r requirements.lock.txt" in dockerfile
    assert "requirements.txt" not in dockerfile.replace("requirements.lock.txt", "")
