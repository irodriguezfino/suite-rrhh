"""Shared comparison colours for the Excel report and Qt preview."""


def comparison_colors(minutes: int | None, *, red: bool = False, suppressed: bool = False) -> tuple[str, str] | None:
    """Return background/text colours; special red controls take precedence."""
    if suppressed:
        return None
    if red:
        return "FDE2E1", "9C0006"
    if minutes is None or minutes == 0:
        return None
    return ("E2F0D9", "215E21") if minutes < 0 else ("FFF4CC", "7A4C00")
