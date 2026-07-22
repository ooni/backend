from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from pathlib import Path


class ProfileMiddleware(BaseHTTPMiddleware):
    """
    Profiles a request, generating an html report on disk
    """

    def __init__(self, app, profiling_active : bool, report_path : str, whitelist: tuple[str]):
        """
        - profiling_active: whether profiling is enabled
        - report_path: local disk path where the report is written
        - whitelist: path prefixes to profile (only matching requests are profiled)
        """
        super().__init__(app)
        self.profiling_active = profiling_active
        self.report_path = report_path
        self.whitelist = whitelist

    async def dispatch(self, request: Request, call_next) -> Response:

        if not self.profiling_active or not self.should_profile(request):
            return await call_next(request)

        # Pyinstrument is only available on development modes
        from pyinstrument import Profiler

        profiler = Profiler()
        profiler.start()
        response = await call_next(request)
        profiler.stop()

        # Save report to a file
        report = profiler.output_html()
        report_path = Path(self.report_path)
        report_path.parent.mkdir(exist_ok=True)
        report_path.touch(exist_ok=True)

        with report_path.open("w") as f:
            f.write(report)

        return response

    def should_profile(self, request: Request) -> bool:
        return request.url.path.startswith(self.whitelist)
