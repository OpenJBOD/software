from microdot import Response, send_file, redirect
from microdot.utemplate import Template
from microdot.auth import BasicAuth
import helpers  # Add this import


def setup_routes(
    app,
    CONFIG,
    psu,
    emc2301,
    ds_sensor,
    ds_rom,
    FAN_TEMPS,
    FAN_SPEEDS,
    VERSION,
    MAC_ADDR,
    BOARD_REV,
    ifconfig,
):
    auth = BasicAuth()
    Response.default_content_type = "text/html"

    @auth.authenticate
    async def check_credentials(request, username, password):
        for user in CONFIG["web"]["users"]:
            if username in CONFIG["web"]["users"][user]["username"]:
                if (
                    helpers.create_hash(password)
                    == CONFIG["web"]["users"][user]["password"]
                ):
                    return user

    @app.route("/static/<path:path>")
    @auth
    def static(request, path):
        if ".." in path:
            return "Not found", 404
        return send_file("gzstatic/" + path, compressed=True, file_extension=".gz")

    @app.route("/power_toggle")
    @auth
    async def power_toggle(req):
        if psu.state():
            psu.off()
        else:
            psu.on()
        return redirect("/")

    @app.route("/reset_rp2040")
    @auth
    async def reset_rp2040(req):
        helpers.reset_rp2040()
        return redirect("/")

    @app.route("/reset_config")
    @auth
    async def reset_config(req):
        helpers.write_config(DEFAULT_CONFIG)
        helpers.reset_rp2040()

    @app.route("/note", methods=["POST"])
    @auth
    async def update_note(req):
        CONFIG["notes"] = req.form["notes"]
        helpers.write_config(CONFIG)
        return redirect("/")

    @app.route("/settings/network", methods=["GET", "POST"])
    @auth
    async def settings_network(req):
        if req.method == "POST":
            CONFIG["network"]["hostname"] = req.form["hostname"]
            CONFIG["network"]["method"] = req.form["ip_method"]
            CONFIG["network"]["ip"] = req.form["ip_address"]
            CONFIG["network"]["subnet_mask"] = req.form["subnet_mask"]
            CONFIG["network"]["gateway"] = req.form["gateway_ip"]
            CONFIG["network"]["dns"] = req.form["dns_ip"]
            helpers.write_config(CONFIG)
            return redirect("/settings/network")
        return Template("settings_network.html").render(config=CONFIG)

    @app.route("/settings/power", methods=["GET", "POST"])
    @auth
    async def settings_power(req):
        if req.method == "POST":
            CONFIG["power"]["on_power_restore"] = req.form["on_power_restore"]
            CONFIG["power"]["on_boot_delay"] = int(req.form["on_boot_delay"])
            CONFIG["power"]["follow_usb"] = bool(req.form.get("follow_usb"))
            CONFIG["power"]["follow_usb_delay"] = int(req.form["follow_usb_delay"])
            CONFIG["power"]["ignore_power_switch"] = bool(
                req.form.get("ignore_power_switch")
            )
            helpers.write_config(CONFIG)
            return redirect("/settings/power")
        return Template("settings_power.html").render(config=CONFIG)

    @app.route("/settings/environment", methods=["GET", "POST"])
    @auth
    async def settings_environ(req):
        if req.method == "POST":
            old_ds18x20 = CONFIG["monitoring"]["use_ext_probe"]
            CONFIG["monitoring"]["use_ext_probe"] = bool(req.form.get("use_ext_probe"))
            CONFIG["monitoring"]["use_ext_fan_ctrl"] = bool(
                req.form.get("use_ext_fan_ctrl")
            )
            CONFIG["monitoring"]["ignore_fan_fail"] = bool(
                req.form.get("ignore_fan_fail")
            )
            for i in range(1, 6):
                CONFIG["fan_curve"][str(i)]["temp"] = int(req.form[f"curve_{i}_c"])
                CONFIG["fan_curve"][str(i)]["fan_p"] = int(req.form[f"curve_{i}_p"])
            helpers.write_config(CONFIG)
            if not old_ds18x20:
                CONFIG["monitoring"]["use_ext_probe"] = False
            return redirect("/settings/environment")
        return Template("settings_environment.html").render(config=CONFIG)

    @app.route("/settings/users", methods=["GET", "POST"])
    @auth
    async def settings_users(req):
        if req.method == "POST":
            for i in range(1, 6):
                if (
                    req.form.get(f"user_{i}_n")
                    != CONFIG["web"]["users"][str(i)]["username"]
                ):
                    CONFIG["web"]["users"][str(i)]["username"] = req.form[f"user_{i}_n"]
                if req.form.get(f"user_{i}_cp"):
                    CONFIG["web"]["users"][str(i)]["password"] = helpers.create_hash(
                        req.form[f"user_{i}_p"]
                    )
            helpers.write_config(CONFIG)
            return redirect("/settings/users")
        return Template("settings_users.html").render(config=CONFIG)

    @app.route("/settings/reset")
    @auth
    async def settings_reset(req):
        return Template("settings_reset.html").render()

    @app.route("/")
    @app.route("/index")
    @auth
    async def index(req):
        response = {
            "config": CONFIG,
            "atx_state": psu.state(),
            "serial": helpers.get_id(),
            "fan_rpm": emc2301.get_fan_speed(edges=3, poles=1),
            "net_info": helpers.get_network_info(ifconfig),
            "board_rev": BOARD_REV,
            "mac_addr": MAC_ADDR,
            "fan_speed_p": helpers.duty_to_percent(emc2301.get_pwm_duty_cycle()),
            "version": VERSION,
            "temp": round(
                (
                    helpers.get_ds18x20_temp(ds_sensor, ds_rom)
                    if CONFIG["monitoring"]["use_ds18x20"]
                    else helpers.get_rp2040_temp()
                ),
                2,
            ),
        }
        return Template("index.html").render(resp=response)

    @app.route("/about")
    @auth
    async def about(req):
        return send_file("gzstatic/about.html", compressed=True, file_extension=".gz")
