# Stand Inventory via Audio Transcription Plan

## Overview
This feature allows users to take stand inventory by recording a voice memo on their phone. The audio is uploaded to the site, where Gemini transcribes and matches the spoken item names to official catalog items. After reviewing the transcribed list, the user submits it to Square. This update will be logged as an **inventory recount** (Physical Count) specifically for the stand location, ensuring it replaces the current stand stock without affecting inventory in the warehouse or any other locations.

## Phase 1: API and Stubbed Gemini Integration (Current Focus)

### 1. Gemini Transcription Stub
Create a backend service/function to simulate the Gemini API call. For now, this will return the hardcoded data provided in the requirements:
```python
def stubbed_gemini_transcription(audio_file):
    # Returns the parsed list of items and counts as a structured format (e.g., list of dicts)
    return [
        {"name": "Dandelion Jelly - 8 oz. (226 g.)", "count": 8, "matched": True},
        {"name": "Wild Wineberry Jelly", "count": 14, "matched": False, "note": "Not found in catalog"},
        # ... rest of the items
    ]
```

### 2. Square Inventory API Integration
Implement the Square API call to update the inventory as a recount.
- **Endpoint**: `/api/inventory/stand_recount` (or similar)
- **Method**: POST
- **Payload**: List of item IDs and their new physical counts.
- **Square API Action**: Use `client.inventory.batch_change_inventory`.
- **Change Type**: Use `PHYSICAL_COUNT`.
    - Set `state` to `INVENTORY_PHYSICAL_COUNT` (or `IN_STOCK` depending on the catalog setup, usually `IN_STOCK` is the state, and the type of change is `PHYSICAL_COUNT`).
    - Set `location_id` specifically to the Stand's location ID.
    - Set `catalog_object_id` (variation ID).
    - Set `quantity` to the exact count provided.
- **Matching**: Before sending to Square, the backend must map the official item names from the Gemini output to their corresponding Square Catalog Object IDs (Variation IDs). 
- **Error Handling**: Skip or flag items marked as "Not found in catalog" (e.g., "Wild Wineberry Jelly"). The UI should eventually handle mapping these.

## Phase 2: Frontend Implementation

### 1. Upload Page
- Create a new page `templates/stand_inventory.html`.
- Add a file upload form accepting audio files (e.g., `.m4a`, `.mp3`, `.wav`).
- Display a loading state while the (stubbed) Gemini processing takes place.

### 2. Review and Edit Table
- Once Gemini returns the data, display it in a table on the same page.
- Columns: Official Item Name, Count, Status (Matched / Not Found).
- Provide inputs for the user to manually adjust counts or map unmatched items to official catalog items using a searchable dropdown.

### 3. Submission to Square
- Add a "Submit to Square" button.
- On click, POST the finalized table data to the Square API integration route created in Phase 1.
- Show a success confirmation or error toast based on the API response.

## Phase 3: Actual Gemini Integration

### 1. Prompt Engineering
- Write a system prompt for the Gemini API that includes:
    - The current list of valid Square catalog items.
    - Instructions to transcribe the audio and strictly match the spoken names to the provided catalog list.
    - Instructions to return a structured JSON response handling typos and flagging unmatched items.

### 2. Audio Processing
- Implement the actual file upload handling and transmission to the Gemini API (using the appropriate Gemini vision/audio model).
- Parse the resulting JSON and feed it into the review table.
