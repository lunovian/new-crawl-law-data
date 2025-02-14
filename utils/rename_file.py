import re


def clean_filename(url):
    """
    Extract and clean filename from URL
    Returns a clean filename without special characters
    """
    # Extract the part between 'luatvietnam.vn/' and '#taive' or '.html'
    match = re.search(r"luatvietnam\.vn/([^#]+?)(?:#|\.html)", url)
    if not match:
        return None

    # Get the relevant part and remove the first directory (usually 'tai-chinh')
    path = match.group(1).split("/", 1)[-1]

    # Remove the ID part at the end (e.g., -381826-d2)
    base_name = re.sub(r"-\d+-d\d+$", "", path)

    # Replace hyphens with spaces and clean up
    clean_name = base_name.replace("-", " ").strip()

    # Keep the ID number for uniqueness
    id_match = re.search(r"-(\d+)-d\d+", path)
    if id_match:
        clean_name += f" {id_match.group(1)}"

    return clean_name


def rename_downloaded_file(original_filename, url, file_type):
    """
    Generate new filename based on URL and file type
    """
    clean_name = clean_filename(url)
    if not clean_name:
        return original_filename

    # Add appropriate extension
    extension = ".docx" if file_type.lower() == "doc" else ".pdf"
    return f"{clean_name}{extension}"
