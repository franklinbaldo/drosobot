use drosobot_sim::wifi::{locate,synthetic_reference,Estimate,Parameters};
fn main(){
    let (anchors,samples)=synthetic_reference();
    println!("DrosoBot hypothetical Wi-Fi room fingerprinting (SYNTHETIC; no scans performed)");
    for sample in &samples {
        let estimate=locate(sample,&anchors,sample.tick,Parameters::default());
        match estimate {
            Estimate::Region{id,heuristic_distance_db,..}=>println!("tick={} region={} heuristic_distance_db={:.2}",sample.tick,id,heuristic_distance_db),
            Estimate::Unknown(reason)=>println!("tick={} unknown_reason={}",sample.tick,reason),
        }
    }
}
