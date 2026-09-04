"""Shared control capability classifications used by synthesis and reporting."""

# These controls require browser capture APIs or Google Drive-backed file
# storage that the generated runtime does not yet provide. Render them as
# explicit blockers instead of empty generic containers.
EXPLICITLY_UNSUPPORTED_INPUTS = {
    "AddMediaButton",
    "Attachments",
    "BarcodeReader",
    "BarcodeScanner",
    "Camera",
    "Microphone",
    "PenInput",
}
