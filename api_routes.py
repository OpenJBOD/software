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

    @app.route("/api/fanmode", methods=["GET", "POST"])
    @auth
    async def api_set_fan_ctrl(req):
        if req.method == "POST":
            if "use_ext_fan_ctrl" in req.json and isinstance(req.json["use_ext_fan_ctrl"], (int, float)):
                CONFIG["monitoring"]["use_ext_fan_ctrl"] = req.json["use_ext_fan_ctrl"]
            return {"status": "success"}
        return {"use_ext_fan_ctrl": CONFIG["monitoring"]["use_ext_fan_ctrl"]}

    @app.route("/api/fans", methods=["GET", "POST"])
    @auth
    async def api_set_fans(req):
        if req.method == "POST":
            if "fan0" in req.json and isinstance(req.json["fan0"], (int, float)):
                CONFIG["monitoring"]["use_ext_fan_ctrl"] = True
                duty_cycle = helpers.percent_to_duty(req.json["fan0"])
                emc2301.set_pwm_duty_cycle(duty_cycle)
            return {"status": "success"}
        return {"fan0": helpers.duty_to_percent(emc2301.get_pwm_duty_cycle())}

    @app.route("/api/power")
    @auth
    async def api_get_power(req):
        return {"state": psu.state()}

    @app.route("/api/power/on")
    @auth
    async def api_power_on(req):
        try:
            psu.on()
        except Exception as e:
            return {"status": "error", "message": str(e)}
        
        return {"status": "success"}

    @app.route("/api/power/off")
    @auth
    async def api_power_off(req):
        try:
            psu.off()
        except Exception as e:
            return {"status": "error", "message": str(e)}
        
        return {"status": "success"}

    @app.route("/api/reset/rp2040")
    @auth
    async def api_reset_rp2040(req):
        helpers.reset_rp2040()
        # Return doesn't matter. It's going to restart.
        return {"status": "success"}

    @app.route("/api/reset/config")
    @auth
    async def api_reset_config(req):
        helpers.write_config(DEFAULT_CONFIG)
        helpers.reset_rp2040()
        return {"status": "success"}

    @app.route("/api/note", methods=["GET", "POST"])
    @auth
    async def api_update_note(req):
        if req.method == "POST":
            CONFIG["notes"] = req.json["notes"]
            helpers.write_config(CONFIG)
        return {"notes": CONFIG["notes"]}

    @app.route("/api/settings/network", methods=["GET", "POST"])
    @auth
    async def api_settings_network(req):
        if req.method == "POST":
            CONFIG["network"]["hostname"] = req.json["hostname"]
            CONFIG["network"]["method"] = req.json["ip_method"]
            CONFIG["network"]["ip"] = req.json["ip_address"]
            CONFIG["network"]["subnet_mask"] = req.json["subnet_mask"]
            CONFIG["network"]["gateway"] = req.json["gateway_ip"]
            CONFIG["network"]["dns"] = req.json["dns_ip"]
            helpers.write_config(CONFIG)
            return {"status": "success"}
        return CONFIG["network"]

    @app.route("/api/settings/power", methods=["GET", "POST"])
    @auth
    async def api_settings_power(req):
        if req.method == "POST":
            CONFIG["power"]["on_power_restore"] = req.json["on_power_restore"]
            CONFIG["power"]["on_boot_delay"] = int(req.json["on_boot_delay"])
            CONFIG["power"]["follow_usb"] = bool(req.json.get("follow_usb"))
            CONFIG["power"]["follow_usb_delay"] = int(req.json["follow_usb_delay"])
            CONFIG["power"]["ignore_power_switch"] = bool(req.json.get("ignore_power_switch"))
            helpers.write_config(CONFIG)
            return {"status": "success"}
        return CONFIG["power"]

    @app.route("/api/settings/environment", methods=["GET", "POST"])
    @auth
    async def api_settings_environ(req):
        if req.method == "POST":
            old_ds18x20 = CONFIG["monitoring"]["use_ext_probe"]
            CONFIG["monitoring"]["use_ext_probe"] = bool(req.json.get("use_ext_probe"))
            CONFIG["monitoring"]["use_ext_fan_ctrl"] = bool(req.json.get("use_ext_fan_ctrl"))
            CONFIG["monitoring"]["ignore_fan_fail"] = bool(req.json.get("ignore_fan_fail"))
            for i in range(1, 6):
                CONFIG["fan_curve"][str(i)]["temp"] = int(req.json[f"curve_{i}_c"])
                CONFIG["fan_curve"][str(i)]["fan_p"] = int(req.json[f"curve_{i}_p"])
            helpers.write_config(CONFIG)
            if not old_ds18x20:
                CONFIG["monitoring"]["use_ext_probe"] = False
            return {"status": "success"}
        return CONFIG["monitoring"]

    @app.route("/api/settings/users", methods=["GET", "POST"])
    @auth
    async def api_settings_users(req):
        if req.method == "POST":
            for i in range(1, 6):
                if req.json.get(f"user_{i}_n") != CONFIG["web"]["users"][str(i)]["username"]:
                    CONFIG["web"]["users"][str(i)]["username"] = req.json[f"user_{i}_n"]
                if req.json.get(f"user_{i}_cp"):
                    CONFIG["web"]["users"][str(i)]["password"] = helpers.create_hash(req.json[f"user_{i}_p"])
            helpers.write_config(CONFIG)
            return {"status": "success"}
        return CONFIG["web"]["users"]

    @app.route("/api/status")
    @auth
    async def api_overview(req):
        response = {
            "config": CONFIG,
            "atx_state": psu.state(),
            "serial": helpers.get_id(),
            "fan_rpm": emc2301.get_fan_speed(edges=3, poles=1),
            "net_info": helpers.get_network_info(ifconfig),
            "mac_addr": MAC_ADDR,
            "fan_speed_p": helpers.duty_to_percent(emc2301.get_pwm_duty_cycle()),
            "version": VERSION,
            "temp": round(helpers.get_ds18x20_temp(ds_sensor, ds_rom) if CONFIG["monitoring"]["use_ds18x20"] else helpers.get_rp2040_temp(), 2)
        }
        return response
