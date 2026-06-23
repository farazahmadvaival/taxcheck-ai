import os
import zipfile
from pathlib import Path

def extract_zip(zip_file_path: str, dest_dir: str):
    """
    Extracts the ZIP archive to dest_dir with a strict guardrail against Zip-Slip path traversal attacks.
    """
    dest_path = Path(dest_dir).resolve()
    os.makedirs(dest_path, exist_ok=True)
    
    print(f"Starting safe ZIP extraction from {zip_file_path} to {dest_dir}...")
    
    with zipfile.ZipFile(zip_file_path, "r") as zip_ref:
        for member in zip_ref.infolist():
            # Calculate target path and resolve it to remove relative directories (e.g. ../)
            target_path = Path(dest_path / member.filename).resolve()
            
            # Zip-Slip check: Ensure target path starts with the destination path prefix
            try:
                target_path.relative_to(dest_path)
            except ValueError:
                raise ValueError(
                    f"Security Exception: Path traversal (Zip-Slip) detected in member '{member.filename}'. "
                    f"Attempted to escape destination path."
                )
            
            # If the member is a directory, make it
            if member.is_dir():
                os.makedirs(target_path, exist_ok=True)
            else:
                # Ensure the parent directory exists
                os.makedirs(target_path.parent, exist_ok=True)
                # Extract and write the file
                with zip_ref.open(member) as source, open(target_path, "wb") as target:
                    target.write(source.read())
                    
    print(f"Safe extraction complete for: {zip_file_path}")
