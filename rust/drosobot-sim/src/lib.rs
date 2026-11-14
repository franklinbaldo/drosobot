//! Deliberately synthetic, deterministic closed-loop experiment.
//!
//! The controller receives ONLY the declared, egocentric observation.
//! It never sees pose, obstacles or goal from the simulator. There is no
//! network, HTTP, motor transport or import of the hardware gateway crate.
//! This is not a MaleCNS implementation or a model of ESP-Hi servo physics.

#[derive(Copy, Clone, Debug, Eq, PartialEq)]
pub enum Action {
    Idle,
    Forward,
    TurnLeft,
    TurnRight,
}

#[derive(Copy, Clone, Debug, Eq, PartialEq)]
pub enum ObservationSource {
    Synthetic,
}

/// Hypothetical forward-clearance sensor; NOT available on the verified robot.
/// Missing, future-dated or stale data must not authorize forward movement.
#[derive(Copy, Clone, Debug, Eq, PartialEq)]
pub struct ForwardObstacle {
    pub blocked: bool,
    pub sample_tick: u64,
    pub source: ObservationSource,
}

#[derive(Copy, Clone, Debug, Eq, PartialEq)]
pub struct Observation {
    pub tick: u64,
    pub ahead: Option<ForwardObstacle>,
}

pub trait Controller {
    fn choose(&mut self, observation: &Observation) -> Action;
}

/// Conventional comparator only, NOT MaleCNS or a putative fly brain.
#[derive(Default)]
pub struct ReactiveBaseline;
impl Controller for ReactiveBaseline {
    fn choose(&mut self, observation: &Observation) -> Action {
        match observation.ahead {
            Some(sensor) if sensor.blocked => Action::TurnRight,
            Some(_) => Action::Forward,
            None => Action::Idle,
        }
    }
}

#[derive(Copy, Clone, Debug, Eq, PartialEq)]
pub enum Decision {
    Accepted(Action),
    Rejected(&'static str),
}

/// Only authorizes actions inside this synthetic simulator, never hardware.
#[derive(Copy, Clone, Debug)]
pub struct SimulationGate {
    pub max_sensor_age_ticks: u64,
}

impl SimulationGate {
    pub fn evaluate(&self, observation: &Observation, proposed: Action) -> Decision {
        if proposed == Action::Idle {
            return Decision::Accepted(Action::Idle);
        }
        let Some(sensor) = observation.ahead else {
            return Decision::Rejected("observation_missing");
        };
        if sensor.sample_tick > observation.tick {
            return Decision::Rejected("observation_from_future");
        }
        if observation.tick - sensor.sample_tick > self.max_sensor_age_ticks {
            return Decision::Rejected("observation_stale");
        }
        if proposed == Action::Forward && sensor.blocked {
            return Decision::Rejected("obstacle_ahead");
        }
        Decision::Accepted(proposed)
    }
}

#[derive(Copy, Clone, Debug, Eq, PartialEq)]
pub enum Heading { North, East, South, West }
impl Heading {
    fn turn_left(self) -> Self {
        match self { Self::North => Self::West, Self::West => Self::South,
            Self::South => Self::East, Self::East => Self::North }
    }
    fn turn_right(self) -> Self {
        match self { Self::North => Self::East, Self::East => Self::South,
            Self::South => Self::West, Self::West => Self::North }
    }
    fn delta(self) -> (i32,i32) {
        match self { Self::North => (0,-1), Self::East => (1,0),
            Self::South => (0,1), Self::West => (-1,0) }
    }
}

/// Ground-truth pose, visible only to the simulator/evaluator.
#[derive(Copy, Clone, Debug, Eq, PartialEq)]
pub struct Pose { pub x: i32, pub y: i32, pub heading: Heading }

/// A grid of hard obstacles. One simulated tick is NOT an ESP-Hi motor step.
#[derive(Clone, Debug)]
pub struct GridWorld {
    width: i32,
    height: i32,
    obstacles: Vec<(i32,i32)>,
    pub pose: Pose,
    pub tick: u64,
}
impl GridWorld {
    pub fn new(width:i32, height:i32, start:Pose, obstacles: Vec<(i32,i32)>) -> Result<Self,String> {
        if width <= 0 || height <= 0 || width > 100 || height > 100 {
            return Err("invalid_world_dimensions".into());
        }
        let prototype = Self { width, height, obstacles, pose: start, tick: 0 };
        if prototype.obstacles.iter().any(|&(x,y)| x<0 || y<0 || x>=width || y>=height)
            || prototype.blocked_at(start.x,start.y) {
            return Err("invalid_start_or_obstacle".into());
        }
        Ok(prototype)
    }
    fn blocked_at(&self,x:i32,y:i32)->bool {
        x<0 || x>=self.width || y<0 || y>=self.height || self.obstacles.contains(&(x,y))
    }
    fn front(&self)->(i32,i32) {
        let (dx,dy)=self.pose.heading.delta(); (self.pose.x+dx,self.pose.y+dy)
    }
    pub fn observe(&self)->Observation {
        let (x,y)=self.front();
        Observation { tick:self.tick, ahead:Some(ForwardObstacle {
            blocked:self.blocked_at(x,y),sample_tick:self.tick,source:ObservationSource::Synthetic
        })}
    }
    /// Applies an *approved* simulated action. Collision is counted, not allowed through.
    fn apply(&mut self,action:Action)->(bool,bool) {
        let mut collision=false; let mut advanced=false;
        match action {
            Action::Idle=>{},
            Action::TurnLeft=>self.pose.heading=self.pose.heading.turn_left(),
            Action::TurnRight=>self.pose.heading=self.pose.heading.turn_right(),
            Action::Forward=>{
                let (x,y)=self.front();
                if self.blocked_at(x,y) {collision=true;} else {
                    self.pose.x=x;self.pose.y=y;advanced=true;
                }
            }
        }
        self.tick+=1;
        (collision,advanced)
    }
}

#[derive(Copy, Clone, Debug, Eq, PartialEq)]
pub struct Record {
    pub tick: u64,
    pub ahead_blocked: Option<bool>,
    pub proposed: Action,
    pub executed: Action,
    pub rejected: bool,
    pub collision: bool,
    pub pose_for_evaluator_only: Pose,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct Episode {
    pub records:Vec<Record>,
    pub moves:u64,
    pub collisions:u64,
    pub rejected:u64,
}

pub fn run_episode<C:Controller>(
    mut world:GridWorld, controller:&mut C, gate:SimulationGate, ticks:u64
)->Episode {
    let mut episode=Episode{records:Vec::new(),moves:0,collisions:0,rejected:0};
    for _ in 0..ticks.min(10000) {
        let observation=world.observe();
        let proposed=controller.choose(&observation);
        let decision=gate.evaluate(&observation,proposed);
        let (executed,rejected)=match decision {
            Decision::Accepted(a)=>(a,false), Decision::Rejected(_)=>(Action::Idle,true)
        };
        let (collision,advanced)=world.apply(executed);
        episode.moves+=u64::from(advanced);
        episode.collisions+=u64::from(collision);
        episode.rejected+=u64::from(rejected);
        episode.records.push(Record {tick:observation.tick,
            ahead_blocked:observation.ahead.map(|o|o.blocked),
            proposed,executed,rejected,collision,pose_for_evaluator_only:world.pose});
    }
    episode
}

pub fn reference_world()->GridWorld {
    GridWorld::new(5,4,Pose{x:1,y:1,heading:Heading::East},vec![(3,1),(3,2)]).expect("valid built-in map")
}

#[cfg(test)]
mod tests {
    use super::*;
    fn sensor(blocked:bool, sample_tick:u64, tick:u64)->Observation {
        Observation{tick,ahead:Some(ForwardObstacle{blocked,sample_tick,source:ObservationSource::Synthetic})}
    }
    #[test]
    fn gate_rejects_missing_future_stale_and_obstructed() {
        let g=SimulationGate{max_sensor_age_ticks:1};
        assert_eq!(g.evaluate(&Observation{tick:10,ahead:None},Action::Forward),Decision::Rejected("observation_missing"));
        assert_eq!(g.evaluate(&sensor(false,11,10),Action::Forward),Decision::Rejected("observation_from_future"));
        assert_eq!(g.evaluate(&sensor(false,8,10),Action::Forward),Decision::Rejected("observation_stale"));
        assert_eq!(g.evaluate(&sensor(true,10,10),Action::Forward),Decision::Rejected("obstacle_ahead"));
        assert_eq!(g.evaluate(&sensor(false,10,10),Action::Forward),Decision::Accepted(Action::Forward));
    }
    #[test]
    fn controller_sees_only_egocentric_sensor() {
        let w=reference_world(); let o=w.observe();
        assert_eq!(o.tick,0);
        assert_eq!(o.ahead.unwrap().source,ObservationSource::Synthetic);
        assert!(!o.ahead.unwrap().blocked);
    }
    #[test]
    fn deterministic_closed_loop_with_baseline_and_no_collisions() {
        let one=run_episode(reference_world(),&mut ReactiveBaseline,SimulationGate{max_sensor_age_ticks:0},25);
        let two=run_episode(reference_world(),&mut ReactiveBaseline,SimulationGate{max_sensor_age_ticks:0},25);
        assert_eq!(one,two);
        assert_eq!(one.records.len(),25);
        assert!(one.moves>0);
        assert_eq!(one.collisions,0);
    }
    #[test]
    fn policy_cannot_pass_wall_even_if_it_asks() {
        struct AlwaysForward;
        impl Controller for AlwaysForward {fn choose(&mut self,_:&Observation)->Action{Action::Forward}}
        let e=run_episode(reference_world(),&mut AlwaysForward,SimulationGate{max_sensor_age_ticks:0},10);
        assert_eq!(e.collisions,0);
        assert!(e.rejected>0);
        assert!(e.records.iter().any(|r|r.rejected && r.executed==Action::Idle));
    }
}

/// MaleCNS frozen operator: executable only with verified external artifact.
pub mod malecns;
