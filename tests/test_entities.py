from jujumate.models.entities import AppInfo, CloudInfo, ControllerInfo, ModelInfo, UnitInfo


def test_cloud_info_defaults():
    cloud = CloudInfo(name="aws", type="ec2")
    assert cloud.regions == []
    assert cloud.credentials == []


def test_cloud_info_full():
    cloud = CloudInfo(name="aws", type="ec2", regions=["us-east-1"], credentials=["admin"])
    assert cloud.name == "aws"
    assert cloud.regions == ["us-east-1"]


def test_controller_info():
    ctrl = ControllerInfo(name="prod", cloud="aws", region="us-east-1", juju_version="3.6.0")
    assert ctrl.model_count == 0


def test_model_info_defaults():
    model = ModelInfo(name="dev", controller="prod", cloud="aws", region="us-east-1", status="available")
    assert model.machine_count == 0
    assert model.app_count == 0


def test_app_info_defaults():
    app = AppInfo(name="postgresql", model="dev", charm="postgresql", channel="14/stable", revision=363)
    assert app.unit_count == 0
    assert app.status == ""
    assert app.message == ""


def test_unit_info():
    unit = UnitInfo(name="postgresql/0", app="postgresql", machine="0", workload_status="active", agent_status="idle")
    assert unit.address == ""
