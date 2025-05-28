# Updates

15 may changes:
1. Fixed issue where app reprocessed PDF whenever a form field was edited
- Implemented session state to store extracted data between script reruns
- Added file fingerprinting to detect new uploads vs widget interactions
- Created unique keys for all form widgets to prevent state conflicts

2. UI Update
- Added sidebar
- Added expanders for instructions + disclaimer
- Added tool tip for file upload
- Added .streamlit/config.toml + style.css files for formatting
