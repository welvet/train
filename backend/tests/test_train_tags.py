from train.domain.train_tags import TrainTagRegistry


def test_train_tag_registry_normalizes_hardware_ids() -> None:
    tags = TrainTagRegistry({" 04:a1:b2:c3 ": "arctic_express"})

    assert tags.resolve("04:A1:B2:C3") == "arctic_express"
    assert tags.resolve("de:ad:be:ef") is None


def test_empty_train_tags_and_train_ids_are_not_registered() -> None:
    tags = TrainTagRegistry({"": "ghost_train", "04:AA": "", "04:BB": "  "})

    assert tags.resolve("") is None
    assert tags.resolve("04:AA") is None
    assert tags.resolve("04:BB") is None
