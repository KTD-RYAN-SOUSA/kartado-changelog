def get_record_history(occurrence_record, action_name="approve"):
    if "approve" in occurrence_record.company.metadata["extra_actions"]:
        status = occurrence_record.company.metadata["extra_actions"][action_name][
            "dest_status"
        ]
        hists = occurrence_record.historicaloccurrencerecord.all()
        try:
            hist = next(a for a in hists if str(a.status_id) == status)
            return hist
        except StopIteration:
            return None
