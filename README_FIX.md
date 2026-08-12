# Body Proportions — BackOffice selected generation provider fix

Fix aislado:
- Body Proportions BackOffice resolves preview from config.storage_mode.
- response.image_storage_file_id now returns the StorageFile ID of that selected provider copy.
- Legacy fallback is accepted only when its provider exactly matches the selected generation provider.
- If the selected provider does not contain that preview, no file from another provider is shown.
- AppWeb/Create Model IA active_preview_source is untouched.

This fixes cases where the UI built:
  /api/admin/storage/files/<legacy-id>/content
for a file belonging to a different provider.

No migration. No changes to library copy/activate logic, generation queue, formulas, mappings, billing or other modules.
