import AgentDock from "../../components/agent/AgentDock";
import FirstRun from "../../components/mobile/FirstRun";
import RadarClient from "../../components/RadarClient";

export default function RadarPage() {
  return (
    <>
      <RadarClient />
      <FirstRun />
      <AgentDock />
    </>
  );
}
