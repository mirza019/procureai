"""Generate the README schema image from SQLAlchemy metadata (no database access)."""

from html import escape
from pathlib import Path

from procureai.db import models  # noqa: F401
from procureai.db.base import Base


def main() -> None:
    tables = list(Base.metadata.sorted_tables)
    width, cell_width, cell_height = 1600, 390, 225
    rows = (len(tables) + 3) // 4
    positions = {table.name: (20 + (i % 4) * cell_width, 110 + (i // 4) * cell_height)
                 for i, table in enumerate(tables)}
    height = 160 + rows * cell_height
    parts = [(f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
              f'viewBox="0 0 {width} {height}" role="img" aria-labelledby="title">'),
             '<title id="title">ProcureAI database schema: tables, keys, and foreign-key relationships</title>',
             f'<rect width="{width}" height="{height}" fill="#151216"/>',
             '<text x="25" y="45" fill="#f6f1ff" font-family="Arial" font-size="30">ProcureAI · Database Schema</text>',
             '<text x="25" y="78" fill="#c9c1d1" font-family="Arial" font-size="16">PK = primary key · FK → referenced table · Selected columns shown · All foreign keys listed</text>']
    for table in tables:
        x, y = positions[table.name]
        parts.extend([f'<rect x="{x}" y="{y}" width="370" height="205" rx="12" fill="#241f2b" stroke="#655078"/>',
                      f'<text x="{x + 14}" y="{y + 29}" fill="#e4d6ff" font-family="Arial" font-size="19" font-weight="bold">{escape(table.name)}</text>'])
        lines = []
        for column in table.columns:
            if column.primary_key:
                lines.append(f'PK {column.name}')
            for fk in column.foreign_keys:
                lines.append(f'FK {column.name} → {fk.column.table.name}')
        ordinary = [c.name for c in table.columns if not c.primary_key and not c.foreign_keys]
        if len(lines) < 6:
            lines.extend(ordinary[:6 - len(lines)])
        for j, line in enumerate(lines):
            parts.append(f'<text x="{x + 14}" y="{y + 56 + j * 21}" fill="#c9c1d1" font-family="Arial" font-size="13">{escape(line)}</text>')
    parts.append('</svg>')
    target = Path(__file__).resolve().parents[1] / 'docs/images/database-schema.svg'
    target.write_text('\n'.join(parts), encoding='utf-8')
    print(f'Generated {target}: {len(tables)} tables')


if __name__ == '__main__':
    main()
