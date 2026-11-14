use drosobot_sim::{reference_world,run_episode,ReactiveBaseline,SimulationGate};

fn main(){
    let report=run_episode(reference_world(),&mut ReactiveBaseline,SimulationGate{max_sensor_age_ticks:0},25);
    println!("DrosoBot synthetic closed-loop demonstration (NOT MaleCNS, NOT real ESP-Hi)");
    println!("ticks={} grid_moves={} collisions={} rejected={}",report.records.len(),report.moves,report.collisions,report.rejected);
    println!("controller_input=egocentric_front_obstacle_only; pose=hidden_from_controller");
}
