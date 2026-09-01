# PDF to Markdown

The Documents panel can convert an uploaded, text-based PDF into a stored
Markdown (`.md`) companion. The copy stays in the same domain or sub-domain and
the same virtual folder as its source PDF.

## Use it

1. Open a domain or sub-domain and select **Documents**.
2. Upload a PDF through the existing document drop area.
3. Select **Convert** beside that PDF.
4. A Markdown copy appears directly under the PDF in the same virtual folder.
5. Use **View** to read it in the app or **Download** to save a local copy.

The export begins with the document title and adds a `## Page N` heading for
each page. Page boundaries make the output easier to review against the source
PDF. Repeated short headers and footers are removed using the same local
cleaning step used by document retrieval.

## Privacy and security

- Conversion happens in the local backend. It does not upload the PDF to an
  external conversion service or language model.
- The Markdown companion is stored with the source document and automatically
  follows organizer folder changes.
- The companion is not indexed as another document. The source PDF remains the
  single retrieval record, preventing duplicate search results and citations.
- The endpoint requires the same owner token and exact scope ownership as the
  rest of the document API.
- Only files inside the configured document-storage directory can be read.
- The existing document upload size limit also applies to conversion.
- In-app previews render Markdown with raw HTML and remote images disabled.

## Current limits

This tool extracts an existing text layer with `pypdf`; it is not OCR. Scanned
or image-only PDFs must be processed with an OCR tool before upload. Complex
visual layouts, columns, tables, handwriting, equations, and text embedded in
images may not reproduce faithfully in Markdown. The original PDF remains the
source of truth for layout-sensitive review. Deleting the PDF also deletes its
stored Markdown companion.
