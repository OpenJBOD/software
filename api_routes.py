from microdot import Response
from microdot.auth import BasicAuth
import helpers

def setup_api_routes(app, CONFIG, emc2301, ds_sensor, ds_rom):
    auth = BasicAuth()
    Response.default_content_type = "application/json"

    @app.route("/api/temperatures")
    @auth
    async def api_get_temperatures(req):
        temperatures = {"rp2040": helpers.get_rp2040_temp()}
        if CONFIG["monitoring"]["use_ds18x20"]:
            temperatures["chassis"] = helpers.get_ds18x20_temp(ds_sensor, ds_rom)
        return temperatures

    @app.route("/api/fanmode", methods=["POST"])
    @auth
    async def api_set_fan_ctrl(req):
        if "use_ext_fan_ctrl" in req.json and isinstance(req.json["use_ext_fan_ctrl"], (int, float)):
            CONFIG["monitoring"]["use_ext_fan_ctrl"] = req.json["use_ext_fan_ctrl"]
        return {"status": "success"}

    @app.route("/api/fans", methods=["POST"])
    @auth
    async def api_set_fans(req):
        if "fan0" in req.json and isinstance(req.json["fan0"], (int, float)):
            CONFIG["monitoring"]["use_ext_fan_ctrl"] = True
            duty_cycle = helpers.percent_to_duty(req.json["fan0"])
            emc2301.set_pwm_duty_cycle(duty_cycle)
        return {"status": "success"}
