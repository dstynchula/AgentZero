from agentzero.web.jobs import LIST_VIEW_DEFAULT_COLUMNS, UI_COLUMNS


def test_list_view_defaults_are_subset_of_ui_columns():
    assert set(LIST_VIEW_DEFAULT_COLUMNS) <= set(UI_COLUMNS)
    assert len(LIST_VIEW_DEFAULT_COLUMNS) == 6
