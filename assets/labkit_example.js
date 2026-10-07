// Hand-written reference experiment for the lab kit: shown to the AI as the example to follow (simulation.py)
// and run by the tests. Checked by eye in a browser screenshot (2026-10-06).
const SIM = {
  title: "Electrolysis of water",
  observe: "Switch the current on and compare the gas collected at the two electrodes.",
  state: { on: false, salt: true, gas: 0 },
  controls() {
    labButton("Switch current on/off", () => {
      SIM.state.on = !SIM.state.on;
      labStart("power", 1500);
    });
    labSelect("Water", ["with a little salt", "pure water"], (value) => {
      SIM.state.salt = value === "with a little salt";
      labStart("mix", 1200);
    });
  },
  drawApparatus(area) {
    const s = this.state;
    const bottom = area.y + area.h - 95; // room under the beaker for the battery
    const conducts = s.on && s.salt;
    if (conducts) s.gas = Math.min(1, s.gas + 0.002);
    const beaker = labBeaker(area.x + area.w * 0.42, bottom, {
      w: 260, h: 190, level: 0.75, liquid: "#bfdbfe", swirl: labProgress("mix"),
    });
    const cathodeX = beaker.x - 60, anodeX = beaker.x + 60;
    const mouth = beaker.surface + 30; // inverted tubes stand in the water
    labTestTube(cathodeX, mouth, { inverted: true, h: 150, w: 40, gas: s.gas * 0.66, gasLabel: "H₂" });
    labTestTube(anodeX, mouth, { inverted: true, h: 150, w: 40, gas: s.gas * 0.33, gasLabel: "O₂" });
    // electrodes come up through the bottom of the beaker into the tubes
    labElectrode(cathodeX, mouth - 20, beaker.bottom + 18, { sign: "-" });
    labElectrode(anodeX, mouth - 20, beaker.bottom + 18, { sign: "+" });
    if (conducts) {
      labBubbles(cathodeX, beaker.bottom - 10, mouth - 10, { rate: 1, spread: 6 });
      labBubbles(anodeX, beaker.bottom - 10, mouth - 10, { rate: 0.5, spread: 6 });
    }
    const cell = labBattery(beaker.x, beaker.bottom + 58, { on: s.on });
    // dots move from the first point to the last: electrons flow − terminal → cathode, anode → + terminal
    labWire([[cell.minus.x, cell.minus.y], [cathodeX, cell.minus.y], [cathodeX, beaker.bottom + 18]], { current: conducts });
    labWire([[anodeX, beaker.bottom + 18], [anodeX, cell.plus.y], [cell.plus.x, cell.plus.y]], { current: conducts });
    labLabel("Beaker", beaker.right + 10, beaker.bottom - 30, { size: 12, align: "left" });
    labLabel("Battery", cell.plus.x + 10, cell.plus.y, { size: 12, align: "left" });
  },
  panel() {
    const s = this.state;
    return [
      "Current: " + (s.on ? "on" : "off"),
      { text: s.on && !s.salt ? "Pure water hardly conducts" : "Water: " + (s.salt ? "with salt" : "pure"), bold: true },
      "Gas at cathode (−): hydrogen",
      "Gas at anode (+): oxygen",
      "Volume H₂ : O₂ = 2 : 1",
      "2H₂O → 2H₂ + O₂",
    ];
  },
};
