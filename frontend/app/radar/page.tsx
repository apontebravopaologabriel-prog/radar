import "../perf.css";
import AgentDock from "../../components/agent/AgentDock";
import FirstRun from "../../components/mobile/FirstRun";
import RadarClient from "../../components/RadarClient";

export default function RadarPage() {
  return (
    <>
      <div className="radar-stage">
        <RadarClient />
      </div>
      <FirstRun />
      <AgentDock />
    </>
  );
}
