# Body Proportions — Flexible multi-source preview library

Base: exact clean backend ZIP uploaded after the user said NOT to apply the previous portable-library hotfix.

Architecture:
- Existing `image_storage_file_id` is preserved for backward compatibility.
- New `preview_storage_json` stores per-preset copies by provider.
- New `active_preview_source` is stored per sex (woman/man) in BodyProportionWorkflowConfig.
- Create Model IA resolves previews from the active source.

Features:
1. Copy library source -> target (Local / Cloudflare R2 / Amazon S3), non-destructive.
2. Verify every required ready preview exists and is readable at a source.
3. Activate a source ONLY if verification is complete.
4. Export a portable ZIP from any complete source.
5. Import ZIP into Local/R2/S3. Detects proportions_woman and proportions_man.
6. New generation replaces only the copy for its generated provider and preserves other provider copies.

Safety:
- Source copies are never deleted by migration/copy.
- Activation is blocked when any required preview is missing/unreadable.
- ZIP traversal protection, file count and uncompressed-size limits.
- Male structure is supported by the library layer without enabling male model creation prematurely.
- No changes to billing, Runtime, workflow mapping semantics, formulas, queue buttons or unrelated modules.

Run after applying:
alembic upgrade head
