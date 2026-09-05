from train.domain import TrainTagRegistry


def test_train_tag_registry_normalizes_hardware_ids() -> None:
    tags = TrainTagRegistry({" 04:a1:b2:c3 ": "arctic_express"})

    assert tags.resolve("04:A1:B2:C3") == "arctic_express"
    assert tags.resolve("de:ad:be:ef") is None


def test_multiple_hardware_tags_can_identify_the_same_train() -> None:
    tags = TrainTagRegistry({
        "04:AA": "arctic_express",
        "04:BB": "arctic_express",
    })

    assert tags.resolve("04:AA") == "arctic_express"
    assert tags.resolve("04:BB") == "arctic_express"


def test_empty_train_tags_and_train_ids_are_not_registered() -> None:
    tags = TrainTagRegistry({"": "ghost_train", "04:AA": "", "04:BB": "  "})

    assert tags.resolve("") is None
    assert tags.resolve("04:AA") is None
    assert tags.resolve("04:BB") is None
