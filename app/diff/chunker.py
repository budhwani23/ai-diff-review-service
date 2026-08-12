from dataclasses import dataclass

from app.diff.parser import FileDiff


@dataclass(slots=True)
class ReviewChunk:
    files: list[FileDiff]

    @property
    def raw(self) -> str:
        return "".join(file.raw for file in self.files)

    @property
    def byte_size(self) -> int:
        return sum(file.byte_size for file in self.files)


def chunk_file_diffs(files: list[FileDiff], maximum_bytes: int) -> list[ReviewChunk]:
    chunks: list[ReviewChunk] = []
    current: list[FileDiff] = []
    current_size = 0

    for file_diff in files:
        size = file_diff.byte_size
        if current and current_size + size > maximum_bytes:
            chunks.append(ReviewChunk(files=current))
            current = []
            current_size = 0
        if size > maximum_bytes:
            if current:
                chunks.append(ReviewChunk(files=current))
                current = []
                current_size = 0
            chunks.append(ReviewChunk(files=[file_diff]))
            continue
        current.append(file_diff)
        current_size += size

    if current:
        chunks.append(ReviewChunk(files=current))
    return chunks
