def get_reporting_history(reporting):
    approved_statuses = reporting.company.metadata.get("approved_approval_steps", [])
    hists = reporting.historicalreporting.all()

    try:
        hist = next(a for a in hists if str(a.approval_step_id) in approved_statuses)
        return hist
    except StopIteration:
        return None
