from pathlib import Path


class LocalStorage:
    """Development storage adapter; replaceable by object storage in production."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def path_for(self, tenant_id: str, document_id: str) -> Path:
        return self.root / tenant_id / document_id

    def write(self, tenant_id: str, document_id: str, content: bytes) -> str:
        path = self.path_for(tenant_id, document_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return str(path.relative_to(self.root))

    def read(self, storage_key: str) -> Path:
        root = self.root.resolve()
        path = (root / storage_key).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise FileNotFoundError(storage_key)
        return path

    def delete(self, storage_key: str) -> None:
        try:
            self.read(storage_key).unlink()
        except FileNotFoundError:
            return
