from pydantic import BaseModel


class ReportResponse(BaseModel):
    report_name: str
    download_url: str
    message: str = "Report generated successfully."