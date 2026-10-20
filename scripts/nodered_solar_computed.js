/**
 * Solar computed meters + 8 panel boxes for Node-RED (HA device-only).
 * Mirrors victron scripts/solar_watt_ledger.py helpers.
 *
 * sensor.victron-mppt-1_solar_power: the only charger in use, SmartSolar 100/50 on B.
 * The three BlueSolar 75/15 are unused. sensor.victron-mppt-1_* is not summed.
 * battery-2-mppt_w stays as the Prometheus key and is 0. It does not publish a 75/15.
 * battery-2-pv_w is 0. battery-1-100_50_w is the 100/50 solar W. PWM is retired.
 */

function stateMap(statesArr) {
    const m = {};
    if (!Array.isArray(statesArr)) return m;
    for (const row of statesArr) {
        if (row && row.entity_id) m[row.entity_id] = row.state;
    }
    return m;
}

function num(states, id) {
    const s = states[id];
    if (s === undefined || s === null || s === "unavailable" || s === "unknown") return null;
    const n = parseFloat(s);
    return Number.isFinite(n) ? n : null;
}

const plug_SOCKETS = [
    ["plug-1", "left"],
    ["plug-1", "right"],
    ["plug-2", "left"],
    ["plug-2", "right"],
    ["plug-3", "left"],
    ["plug-3", "right"],
    ["plug-4", "left"],
    ["plug-4", "right"],
    ["plug-5", "left"],
    ["plug-5", "right"],
    ["plug-6", "left"],
    ["plug-6", "right"],
    ["plug-7", "left"],
    ["plug-7", "right"],
    ["plug-8", "left"],
    ["plug-8", "right"],
];

function h5082Id(plug, side) {
    return plug.toLowerCase() + "_" + side;
}

function textState(states, id) {
    const s = states[id];
    if (s === undefined || s === null || s === "unavailable" || s === "unknown") return "";
    return String(s).replace(/\s+/g, " ").trim();
}

/** On/off plus the operator's Where, Load, and Use text. Not a watt calculation. */
function socketSamples(states) {
    return plug_SOCKETS.map(function (pair) {
        const plug = pair[0];
        const side = pair[1];
        const id = h5082Id(plug, side);
        const sw = states["switch.ihoment_plug_" + id];
        const on = sw === "on" ? 1 : sw === "off" ? 0 : null;
        const use = textState(states, "input_select.plug_" + id + "_use") === "dump" ? "dump" : "normal";
        return {
            plug: plug,
            side: side,
            location: textState(states, "input_text.plug_" + plug.toLowerCase() + "_location"),
            load: textState(states, "input_text.plug_" + id + "_load"),
            use: use,
            on: on,
        };
    });
}

function round1(x) {
    if (x === null || x === undefined || !Number.isFinite(x)) return null;
    return Math.round(x * 10) / 10;
}

function halfString(w) {
    return w === null ? null : round1(w / 2);
}

function meter-1A3Live(states) {
    const v = num(states, "sensor.meter-1_a3_voltage");
    const p = num(states, "sensor.meter-1_a3_power");
    const sgv = num(states, "sensor.sungold-inverter-1_grid_voltage");
    const sga = num(states, "sensor.sungold-inverter-1_grid_current");
    if (v === null || p === null || v < 80) return null;
    if (sgv !== null && sga !== null && sgv < 50 && sga < 0.5 && Math.abs(p) > 5) return null;
    return p;
}

function meter-1B3Live(states) {
    const v = num(states, "sensor.meter-1_b3_voltage");
    const p = num(states, "sensor.meter-1_b3_power");
    if (v === null || p === null || v < 80) return null;
    return Math.abs(p);
}

function kuRenogyAcProxy(states) {
    const sgP = num(states, "sensor.sungold-inverter-1_charging_power");
    if (sgP !== null && sgP >= 15) return 0;
    const b3 = meter-1B3Live(states);
    if (b3 !== null && b3 >= 0.5) return b3;
    const a3 = meter-1A3Live(states);
    if (a3 !== null) return Math.abs(a3);
    return null;
}

/** Legacy 8 panel boxes; per-panel est_w mostly null until BLE keys land. */
function panelBoxes() {
    return [
        {
            id: 1,
            label: "P1",
            string: "B 100/50 2s5p A",
            connects: "B SmartSolar 100/50 (2s5p; 4 panels still on the way)",
            est_w: null,
        },
        {
            id: 2,
            label: "P2",
            string: "B 100/50 2s5p B",
            connects: "B SmartSolar 100/50 (2s5p; 4 panels still on the way)",
            est_w: null,
        },
        {
            id: 3,
            label: "P3",
            string: "unused 75/15",
            connects: "Unused BlueSolar 75/15 (present, not charging)",
            est_w: null,
        },
        {
            id: 4,
            label: "P4",
            string: "unused 75/15",
            connects: "Unused BlueSolar 75/15 (present, not charging)",
            est_w: null,
        },
        {
            id: 5,
            label: "P5",
            string: "unused 75/15",
            connects: "Unused BlueSolar 75/15 (present, not charging)",
            est_w: null,
        },
        {
            id: 6,
            label: "P6",
            string: "unused 75/15",
            connects: "Unused BlueSolar 75/15 (present, not charging)",
            est_w: null,
        },
        {
            id: 7,
            label: "P7 (PWM removed)",
            string: "PWM removed",
            connects: "PWM removed",
            est_w: null,
        },
        {
            id: 8,
            label: "P8 (PWM removed)",
            string: "PWM removed",
            connects: "PWM removed",
            est_w: null,
        },
    ];
}

function computeSolarDerived(statesArr) {
    const states = stateMap(statesArr);
    const ku100 = num(states, "sensor.victron-mppt-1_solar_power");
    const b1 = num(states, "sensor.battery_1_power");
    const b2 = num(states, "sensor.battery_2_power");
    const sgPv = num(states, "sensor.sungold-inverter-1_pv_power");
    const sgLoad = num(states, "sensor.sungold-inverter-1_load_power");
    const sgBatt = num(states, "sensor.sungold-inverter-1_charging_power");
    const sgGridV = num(states, "sensor.sungold-inverter-1_grid_voltage");
    const sgGridA = num(states, "sensor.sungold-inverter-1_grid_current");
    const sgAcIn =
        sgGridV !== null && sgGridA !== null ? round1(Math.abs(sgGridV * sgGridA)) : null;

    // No A charger. + into A is Battery 1 W plus Sungold charging W.
    const t2Load = sgBatt !== null && sgBatt >= 0 ? sgBatt : 0;
    const jumper = b1 !== null ? round1(b1 + t2Load) : null;
    const kuAc = kuRenogyAcProxy(states);
    let kuCombined = null;
    if (b2 !== null && jumper !== null && kuAc !== null) {
        kuCombined = round1(b2 - jumper + kuAc);
    }
    const pwmEst = null;
    const mppt23Est = null;
    const kuShare = kuCombined !== null ? round1(kuCombined / 2) : null;

    // Only the SmartSolar 100/50. The three BlueSolar 75/15 are unused.
    const kuPvForSite = ku100;
    let siteSolar = null;
    if (sgPv !== null && kuPvForSite !== null) {
        siteSolar = round1(sgPv + kuPvForSite);
    } else if (sgPv !== null) {
        siteSolar = round1(sgPv);
    } else if (kuPvForSite !== null) {
        siteSolar = round1(kuPvForSite);
    }

    const batt1Charge = b1 !== null && b1 > 0 ? round1(b1) : 0;
    const siteSource = round1(batt1Charge + (sgAcIn || 0) + (sgPv || 0));
    const siteLoad = sgLoad !== null ? round1(sgLoad) : null;
    const loadUnaccounted =
        siteSolar !== null && siteLoad !== null ? round1(siteSolar - siteLoad) : null;
    const sungoldCartToLoad =
        sgLoad !== null && kuAc !== null ? round1(Math.max(0, sgLoad - kuAc)) : null;

    const panels = panelBoxes();

    return {
        battery-2-mppt_w: 0,
        battery-2-pv_w: 0,
        battery-1-100_50_w: ku100,
        paired_75_15_w: null,
        battery-2-mppt_charge_w: 0,
        battery-2-battery-1-jumper_w: jumper,
        battery-1-victron_mppt23_est_w: mppt23Est,
        battery-1-pwm_mppt_combined_est_w: kuCombined,
        battery-1-pwm_est_w: pwmEst,
        battery-1-charger_equal_share_w: kuShare,
        meter-1_a3_live_w: meter-1A3Live(states),
        meter-1_b3_live_w: meter-1B3Live(states),
        trailer_outlet_w: kuAc,
        sungold_pv_w: sgPv,
        sungold_ac_in_w: sgAcIn,
        sungold_batt_in_w: sgBatt,
        sungold_ac_out_w: sgLoad,
        sungold_cart_to_load_w: sungoldCartToLoad,
        site_solar_w: siteSolar,
        site_source_w: siteSource,
        site_total_load_w: siteLoad,
        load_unaccounted_w: loadUnaccounted,
        battery_1_w: b1,
        battery_2_w: b2,
        panels,
        sockets: socketSamples(states),
    };
}

module.exports = {
    stateMap,
    num,
    round1,
    panelBoxes,
    socketSamples,
    computeSolarDerived,
};
