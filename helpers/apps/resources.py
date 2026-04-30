def get_board_item_relation_qs(obj):
    board_item_relations = [
        "contract_item_administration_workers",
        "contract_item_administration_equipment",
        "contract_item_administration_vehicles",
    ]
    board_item_relation_qs = next(
        (
            getattr(obj, item_relation).all()
            for item_relation in board_item_relations
            if hasattr(obj, item_relation) and getattr(obj, item_relation).exists()
        ),
        None,
    )

    return board_item_relation_qs
