import tempfile

from apps.occurrence_records.helpers.gen.pdf import PDFGeneratorBase
from helpers.aws import upload_to_s3


def render_template_as_pdf(
    pdf: PDFGeneratorBase,
    upload_pdf_to_s3: str = True,
    bucket_name: str = None,
) -> str:
    """
    Render a html template and convert to PDF. Returns the URL of the uploaded file
    if `upload_pdf_to_s3=True` or the path to the local file.

    WARN: If upload_pdf_to_s3 is True you should always provide the bucket_name.

    Args:
        template_path (str): Path to the Django html template.
        context (Any): The data used by the Django html template.
        upload_pdf_to_s3 (str, optional): If the file should be uploaded to S3. Defaults to True.
        bucket_name (str, optional): Which S3 bucket is going to be used for the upload. Defaults to None.

    Returns:
        str: Path to the PDF file (can be a local path or an URL).
    """

    # Raise error the upload_pdf_to_s3 is True but no bucket name was provided
    if upload_pdf_to_s3 and not bucket_name:
        raise ValueError(
            "Please provide a bucket name if the PDF is going to be uploaded to S3"
        )

    # We'll use a temp file before the upload
    file_name = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    pdf_file_path = file_name.name

    pdf.build_pdf(pdf_file_path)

    # If the file is not going to be uploaded to s3, return the path to the temp file
    if not upload_pdf_to_s3:
        return pdf_file_path

    # Upload to S3 and return the URL to the file
    pdf_url = upload_to_s3(pdf_file_path, bucket_name)
    return pdf_url
