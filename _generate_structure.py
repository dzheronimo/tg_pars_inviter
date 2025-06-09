import os

EXCLUDED_DIRS = {
    "__pycache__",
    ".git",
    ".idea",
    ".venv",
    "env",
    ".env",
    ".mypy_cache",
    ".pytest_cache",
    "node_modules",
    "dist",
    "build",
}


def list_dir_tree(root_dir, prefix=""):
    entries = []
    with os.scandir(root_dir) as it:
        for entry in sorted(it, key=lambda e: (not e.is_dir(), e.name.lower())):
            if entry.name in EXCLUDED_DIRS:
                continue
            path = os.path.join(root_dir, entry.name)
            if entry.is_dir():
                entries.append(f"{prefix}📁 {entry.name}/")
                entries += list_dir_tree(path, prefix + "│   ")
            else:
                entries.append(f"{prefix}📄 {entry.name}")
    return entries


def generate_structure(root_path: str, output_file: str = "project_structure.txt"):
    print(f"📦 Генерация структуры проекта: {root_path}")
    tree = list_dir_tree(root_path)
    output = "\n".join(tree)

    with open(output_file, "w", encoding="utf-8") as f:
        f.write(output)

    print(f"✅ Структура сохранена в файл: {output_file}")


if __name__ == "__main__":
    import sys

    path = sys.argv[1] if len(sys.argv) > 1 else "."
    generate_structure(path)
