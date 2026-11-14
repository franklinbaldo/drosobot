//! Paired, reproducible neural observer beside one conventional controller.
//! Not a trained MaleCNS controller; no actions are selected by this brain.
use drosobot_sim::{reference_world,run_episode,Action,Controller,Observation,ReactiveBaseline,SimulationGate};
use drosobot_sim::malecns::{Brain,TargetMap};
use std::{env,fs,path::Path};

#[derive(Clone,Debug)]
struct Ports {left_input:Vec<usize>,right_input:Vec<usize>,left_dn:Vec<usize>,right_dn:Vec<usize>}
impl Ports {
    fn read(path:&Path,neurons:usize)->Result<Self,String>{
        let text=fs::read_to_string(path).map_err(|_|"missing provenance ports")?;
        let mut lists=std::collections::BTreeMap::new();
        for line in text.lines(){
            let mut parts=line.split_ascii_whitespace();
            let group=parts.next().ok_or("empty port group")?;
            if !matches!(group,"vpl"|"vpr"|"dnl"|"dnr") || lists.contains_key(group){return Err("duplicate/unknown port group".into());}
            let mut values=Vec::new();
            for raw in parts {
                let n=raw.parse::<usize>().map_err(|_|"invalid port index")?;
                if n>=neurons{return Err("port index out of bounds".into());}
                values.push(n);
            }
            if values.is_empty(){return Err("empty port group".into());}
            lists.insert(group.to_owned(),values);
        }
        if lists.len()!=4 {return Err("missing required port group".into());}
        Ok(Self{
            left_input:lists.remove("vpl").unwrap(),right_input:lists.remove("vpr").unwrap(),
            left_dn:lists.remove("dnl").unwrap(),right_dn:lists.remove("dnr").unwrap()})
    }
}

struct Shadow {
    brain:Brain,
    mapping:TargetMap,
    ports:Ports,
    baseline:ReactiveBaseline,
    responses:Vec<f32>,
    failed:bool,
}
impl Shadow {
    fn new(brain:Brain,ports:Ports,mapping:TargetMap)->Self{
        Self{brain,ports,mapping,baseline:ReactiveBaseline,responses:Vec::new(),failed:false}
    }
}
impl Controller for Shadow {
    fn choose(&mut self,observation:&Observation)->Action{
        if self.failed {return Action::Idle;}
        let Some(sensor)=observation.ahead else {return Action::Idle;};
        // Explicit *engineered* drive: a binary synthetic frontal obstacle is
        // injected as left-side salience and clear space as right-side salience.
        // This mapping is neither natural fly sensory transduction nor learning.
        let (left,right)=if sensor.blocked {(0.8f32,0.1f32)} else {(0.1,0.8)};
        let mut input=Vec::with_capacity(self.ports.left_input.len()+self.ports.right_input.len());
        input.extend(self.ports.left_input.iter().map(|&i|(i,left)));
        input.extend(self.ports.right_input.iter().map(|&i|(i,right)));
        if self.brain.step(&input,self.mapping).is_err() {self.failed=true;return Action::Idle;}
        let result=self.brain.average(&self.ports.right_dn).and_then(|r| {
            self.brain.average(&self.ports.left_dn).map(|l|r-l)
        });
        match result {Ok(signal)=>self.responses.push(signal),Err(_)=>{self.failed=true;return Action::Idle;}}
        self.baseline.choose(observation) // actions ALWAYS from conventional controller
    }
}
fn run()->Result<(),String>{
    let args:Vec<_>=env::args().skip(1).collect();
    if args.len()!=2 {return Err("Usage: malecns-probe verified.mcns verified-ports.txt".into());}
    let brain=Brain::from_file(Path::new(&args[0]))?;
    let ports=Ports::read(Path::new(&args[1]),brain.neurons)?;
    let n=brain.neurons;let edges=brain.edges;
    let mut original=Shadow::new(brain.clone(),ports.clone(),TargetMap::Original);
    let mut permutation=Shadow::new(brain,ports,TargetMap::Permuted);
    let baseline=run_episode(reference_world(),&mut original,SimulationGate{max_sensor_age_ticks:0},25);
    let counterfactual=run_episode(reference_world(),&mut permutation,SimulationGate{max_sensor_age_ticks:0},25);
    if original.failed || permutation.failed || original.responses.len()!=25 || permutation.responses.len()!=25 {
        return Err("neural observer failed".into());
    }
    if baseline.collisions!=0 || baseline!=counterfactual {
        return Err("shadow observer influenced actions or collision behavior".into());
    }
    let energy=|v:&Vec<f32>| v.iter().map(|x|(*x as f64).powi(2)).sum::<f64>()/v.len() as f64;
    let delta=original.responses.iter().zip(&permutation.responses).map(|(x,y)|(*x as f64-*y as f64).abs()).sum::<f64>()/25.;
    println!("status=shadow_only_not_a_controller");
    println!("neurons={n} edges={edges} ticks=25 moves={} collisions={}",baseline.moves,baseline.collisions);
    println!("male_cns_dn_difference_energy={:.10}",energy(&original.responses));
    println!("target_permutation_dn_difference_energy={:.10}",energy(&permutation.responses));
    println!("mean_abs_response_difference={delta:.10}");
    println!("motor_source=conventional_reactive_baseline; physical_motors=none");
    Ok(())
}
fn main(){if let Err(e)=run(){eprintln!("MaleCNS probe failed: {e}");std::process::exit(1)}}
