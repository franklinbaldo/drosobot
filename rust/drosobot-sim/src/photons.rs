//! A synthetic space-time event field. No Wi-Fi, motors or real optical photons.
//!
//! A moving *virtual* emitter creates rays in a known canonical room. The
//! receiver gets only time-stamped emissions and surface-interaction samples,
//! not obstacle bounds. Object IDs on contact events are an explicit semantic
//! oracle: reconstructing unlabeled surfaces is a separate research problem.
//! This is NOT physical time-of-flight positioning or MaleCNS input yet.

use std::collections::{BTreeMap, BTreeSet};

pub const MAGIC: &[u8; 4] = b"DPH1";
pub const MAX_EVENTS: u32 = 512;
pub const SPEED_MM_PER_TICK: i32 = 1000;
const WIRE_HEADER: usize = 20;

#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct Vec2 {
    pub x: i32,
    pub y: i32,
}
impl Vec2 {
    pub const fn new(x: i32, y: i32) -> Self { Self { x, y } }
    pub fn shifted(self, speed: Vec2, ticks: u32) -> Option<Self> {
        let x = i64::from(self.x) + i64::from(speed.x) * i64::from(ticks);
        let y = i64::from(self.y) + i64::from(speed.y) * i64::from(ticks);
        Some(Self::new(i32::try_from(x).ok()?, i32::try_from(y).ok()?))
    }
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum Kind {
    /// No object geometry is included in this initialization message.
    Epoch { width_mm: i32, height_mm: i32, origin_ms: u64, tick_ms: u32 },
    Emitted { photon: u32, at: Vec2, velocity: Vec2 },
    Contact { photon: u32, object: u32, at: Vec2, normal: Vec2 },
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Event {
    pub scene: u32,
    pub sequence: u32,
    pub tick: u32,
    pub kind: Kind,
}

fn append_u32(out: &mut Vec<u8>, n: u32) { out.extend_from_slice(&n.to_le_bytes()); }
fn append_i32(out: &mut Vec<u8>, n: i32) { out.extend_from_slice(&n.to_le_bytes()); }
fn u32_at(data: &[u8], start: usize) -> u32 {
    u32::from_le_bytes(data[start..start + 4].try_into().expect("checked wire size"))
}
fn i32_at(data: &[u8], start: usize) -> i32 {
    i32::from_le_bytes(data[start..start + 4].try_into().expect("checked wire size"))
}

impl Event {
    /// A small versioned wire format that can later be carried over UDP or TCP.
    /// IMPORTANT: no integrity/MAC/authentication; do not expose to untrusted LAN.
    pub fn encode(&self) -> Vec<u8> {
        let (kind, size) = match self.kind {
            Kind::Epoch { .. } => (0_u8, 20),
            Kind::Emitted { .. } => (1, 20),
            Kind::Contact { .. } => (2, 24),
        };
        let mut out = Vec::with_capacity(WIRE_HEADER + size);
        out.extend_from_slice(MAGIC);
        out.extend_from_slice(&[1, kind, 0, 0]);
        append_u32(&mut out, self.scene);
        append_u32(&mut out, self.sequence);
        append_u32(&mut out, self.tick);
        match self.kind {
            Kind::Epoch { width_mm, height_mm, origin_ms, tick_ms } => {
                append_i32(&mut out, width_mm);
                append_i32(&mut out, height_mm);
                out.extend_from_slice(&origin_ms.to_le_bytes());
                append_u32(&mut out, tick_ms);
            }
            Kind::Emitted { photon, at, velocity } => {
                append_u32(&mut out, photon);
                append_i32(&mut out, at.x);
                append_i32(&mut out, at.y);
                append_i32(&mut out, velocity.x);
                append_i32(&mut out, velocity.y);
            }
            Kind::Contact { photon, object, at, normal } => {
                append_u32(&mut out, photon);
                append_u32(&mut out, object);
                append_i32(&mut out, at.x);
                append_i32(&mut out, at.y);
                append_i32(&mut out, normal.x);
                append_i32(&mut out, normal.y);
            }
        }
        out
    }

    pub fn decode(data: &[u8]) -> Result<Self, &'static str> {
        if data.len() < WIRE_HEADER || &data[..4] != MAGIC || data[4] != 1
            || data[6] != 0 || data[7] != 0 { return Err("invalid_header"); }
        let expected = match data[5] { 0 | 1 => WIRE_HEADER + 20, 2 => WIRE_HEADER + 24,
            _ => return Err("unknown_event_type") };
        if data.len() != expected { return Err("invalid_packet_length"); }
        let scene = u32_at(data, 8);
        let sequence = u32_at(data, 12);
        let tick = u32_at(data, 16);
        if scene == 0 || sequence >= MAX_EVENTS || tick > 1_000_000 {
            return Err("invalid_identity_or_timestamp");
        }
        let kind = match data[5] {
            0 => Kind::Epoch {
                width_mm: i32_at(data, 20), height_mm: i32_at(data, 24),
                origin_ms: u64::from_le_bytes(data[28..36].try_into().expect("checked")),
                tick_ms: u32_at(data, 36),
            },
            1 => Kind::Emitted { photon: u32_at(data, 20),
                at: Vec2::new(i32_at(data, 24), i32_at(data, 28)),
                velocity: Vec2::new(i32_at(data, 32), i32_at(data, 36)) },
            2 => Kind::Contact { photon: u32_at(data, 20), object: u32_at(data, 24),
                at: Vec2::new(i32_at(data, 28), i32_at(data, 32)),
                normal: Vec2::new(i32_at(data, 36), i32_at(data, 40)) },
            _ => unreachable!(),
        };
        match kind {
            Kind::Epoch { width_mm, height_mm, tick_ms, .. }
                if !(100..=100_000).contains(&width_mm)
                    || !(100..=100_000).contains(&height_mm)
                    || !(1..=60_000).contains(&tick_ms) => Err("invalid_epoch"),
            Kind::Emitted { photon, velocity, .. }
                if photon == 0 || photon > 256 || !cardinal_speed(velocity) =>
                    Err("invalid_emission"),
            Kind::Contact { photon, object, normal, .. }
                if photon == 0 || photon > 256 || object == 0 || object > 64
                    || !cardinal_normal(normal) => Err("invalid_contact"),
            _ => Ok(Self { scene, sequence, tick, kind }),
        }
    }
}

fn cardinal_speed(v: Vec2) -> bool {
    (v.x.checked_abs() == Some(SPEED_MM_PER_TICK) && v.y == 0)
        || (v.y.checked_abs() == Some(SPEED_MM_PER_TICK) && v.x == 0)
}
fn cardinal_normal(v: Vec2) -> bool {
    (v.x.checked_abs() == Some(1) && v.y == 0) || (v.y.checked_abs() == Some(1) && v.x == 0)
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Rect { pub min: Vec2, pub max: Vec2 }

/// Ground-truth geometry exists ONLY on this sender/evaluator side.
#[derive(Clone, Debug)]
pub struct CanonicalRoom {
    pub width_mm: i32,
    pub height_mm: i32,
    pub objects: [(u32, Rect); 2],
}
impl Default for CanonicalRoom {
    fn default() -> Self {
        Self { width_mm: 10_000, height_mm: 8_000, objects: [
            (1, Rect { min: Vec2::new(2_000, 2_000), max: Vec2::new(4_000, 4_000) }),
            (2, Rect { min: Vec2::new(6_000, 4_000), max: Vec2::new(8_000, 6_000) }),
        ] }
    }
}

impl CanonicalRoom {
    /// First axis-aligned intersection, not a physical 3-D optics/radio model.
    fn cast(&self, at: Vec2, speed: Vec2) -> Option<(u32, Vec2, Vec2, u32)> {
        let mut closest: Option<(u32, Vec2, Vec2, u32)> = None;
        for &(object, rect) in &self.objects {
            let hit = if speed.x > 0 && (rect.min.y..rect.max.y).contains(&at.y)
                && at.x <= rect.min.x {
                Some((rect.min.x - at.x, Vec2::new(-1, 0)))
            } else if speed.x < 0 && (rect.min.y..rect.max.y).contains(&at.y)
                && at.x >= rect.max.x {
                Some((at.x - rect.max.x, Vec2::new(1, 0)))
            } else if speed.y > 0 && (rect.min.x..rect.max.x).contains(&at.x)
                && at.y <= rect.min.y {
                Some((rect.min.y - at.y, Vec2::new(0, -1)))
            } else if speed.y < 0 && (rect.min.x..rect.max.x).contains(&at.x)
                && at.y >= rect.max.y {
                Some((at.y - rect.max.y, Vec2::new(0, 1)))
            } else { None };
            if let Some((distance_mm, normal)) = hit {
                if distance_mm > 0 && distance_mm % SPEED_MM_PER_TICK == 0 {
                    let ticks = u32::try_from(distance_mm / SPEED_MM_PER_TICK).ok()?;
                    let position = at.shifted(speed, ticks)?;
                    if closest.map_or(true, |other| ticks < other.3) {
                        closest = Some((object, position, normal, ticks));
                    }
                }
            }
        }
        closest
    }

    pub fn make_journal(&self) -> Vec<Event> {
        // One VIRTUAL moving source samples both rectangles from four sides.
        // This sampling schedule is synthetic calibration, NOT a real robot sensor.
        let rays = [
            (Vec2::new(0, 3_000), Vec2::new(1_000, 0)),
            (Vec2::new(10_000, 3_000), Vec2::new(-1_000, 0)),
            (Vec2::new(3_000, 0), Vec2::new(0, 1_000)),
            (Vec2::new(3_000, 8_000), Vec2::new(0, -1_000)),
            (Vec2::new(0, 5_000), Vec2::new(1_000, 0)),
            (Vec2::new(10_000, 5_000), Vec2::new(-1_000, 0)),
            (Vec2::new(7_000, 0), Vec2::new(0, 1_000)),
            (Vec2::new(7_000, 8_000), Vec2::new(0, -1_000)),
        ];
        let scene = 0x4452_4f53; // 'DROS'; not a home or user identifier.
        let mut messages = vec![Event { scene, sequence: 0, tick: 0,
            kind: Kind::Epoch { width_mm: self.width_mm, height_mm: self.height_mm,
                origin_ms: 1_900_000_000_000, tick_ms: 50 } }];
        for (index, &(at, velocity)) in rays.iter().enumerate() {
            let photon = index as u32 + 1;
            let tick = 1 + index as u32 * 12;
            messages.push(Event { scene, sequence: photon * 2 - 1, tick,
                kind: Kind::Emitted { photon, at, velocity } });
            let (object, position, normal, flight) = self.cast(at, velocity)
                .expect("the synthetic beam has a known target");
            messages.push(Event { scene, sequence: photon * 2, tick: tick + flight,
                kind: Kind::Contact { photon, object, at: position, normal } });
        }
        messages
    }
}

/// A synchronized logical clock, NOT a measurement of radio propagation time.
/// `offset_ms` is an estimate of sender_time - receiver_time from an external
/// time synchronization procedure; its uncertainty must be considered.
#[derive(Clone, Copy, Debug)]
pub struct ClockAnchor {
    pub origin_ms: u64,
    pub tick_ms: u32,
}
impl ClockAnchor {
    pub fn now_tick(&self, receiver_wall_ms: u64, offset_ms: i64,
                    uncertainty_ms: u32, maximum_uncertainty_ms: u32) -> Option<u32> {
        if self.tick_ms == 0 || uncertainty_ms > maximum_uncertainty_ms
            || u64::from(uncertainty_ms) * 2 >= u64::from(self.tick_ms) { return None; }
        let sender_now = i128::from(receiver_wall_ms) + i128::from(offset_ms);
        let elapsed = sender_now - i128::from(self.origin_ms);
        if elapsed < 0 { return None; }
        u32::try_from(elapsed / i128::from(self.tick_ms)).ok()
    }
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct SurfaceEstimate {
    pub object: u32,
    pub min: Vec2,
    pub max: Vec2,
    /// Distinct observed surface normals, not a confidence probability.
    pub faces: BTreeSet<(i32, i32)>,
    pub hit_samples: usize,
}
impl SurfaceEstimate {
    pub fn complete_axis_aligned_rectangle(&self) -> bool { self.faces.len() == 4 }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct PhotonPosition {
    pub at: Vec2,
    pub last_evidence_tick: u32,
    pub reflected: bool,
}

/// Stores only authenticated-in-a-future-transport events; this lab does not
/// include transport authentication or real LAN I/O. Never drive hardware from it.
#[derive(Debug)]
pub struct EventReceiver {
    scene: u32,
    messages: BTreeMap<u32, Event>,
    duplicate_count: u32,
}
impl EventReceiver {
    pub fn new(scene: u32) -> Self { Self { scene, messages: BTreeMap::new(), duplicate_count: 0 } }
    pub fn received(&self) -> usize { self.messages.len() }
    pub fn duplicates(&self) -> u32 { self.duplicate_count }

    pub fn ingest(&mut self, packet: &[u8]) -> Result<bool, &'static str> {
        let event = Event::decode(packet)?;
        if event.scene != self.scene { return Err("foreign_scene"); }
        if matches!(&event.kind, Kind::Epoch { .. }) && (event.sequence != 0 || event.tick != 0) {
            return Err("unexpected_epoch_sequence");
        }
        if !matches!(&event.kind, Kind::Epoch { .. }) && event.sequence == 0 {
            return Err("missing_epoch_record");
        }
        if let Some(old) = self.messages.get(&event.sequence) {
            if old != &event { return Err("sequence_conflict"); }
            self.duplicate_count += 1;
            return Ok(false);
        }
        self.messages.insert(event.sequence, event);
        Ok(true)
    }

    pub fn epoch(&self) -> Option<(i32, i32, ClockAnchor)> {
        match &self.messages.get(&0)?.kind {
            Kind::Epoch { width_mm, height_mm, origin_ms, tick_ms } => Some((*width_mm, *height_mm,
                ClockAnchor { origin_ms: *origin_ms, tick_ms: *tick_ms })),
            _ => None,
        }
    }

    /// Missing sequence IDs are supplied by a trusted sender's high-watermark.
    /// Real transports would require a replay request or an event-log snapshot.
    pub fn missing_through(&self, highest_sequence: u32) -> Result<Vec<u32>, &'static str> {
        if highest_sequence >= MAX_EVENTS { return Err("excessive_sequence_range"); }
        Ok((0..=highest_sequence).filter(|seq| !self.messages.contains_key(seq)).collect())
    }

    fn valid_contacts(&self) -> Vec<(u32, u32, Vec2, Vec2)> {
        let Some((width, height, _)) = self.epoch() else { return Vec::new(); };
        let mut launches = BTreeMap::new();
        for event in self.messages.values() {
            if let Kind::Emitted { photon, at, velocity } = event.kind {
                if inside(at, width, height) {
                    // Refuse ambiguous duplicate photon IDs with different events.
                    launches.entry(photon).or_insert((event.tick, at, velocity));
                }
            }
        }
        let mut hits = Vec::new();
        let mut seen_photons = BTreeSet::new();
        for event in self.messages.values() {
            let Kind::Contact { photon, object, at, normal } = event.kind else { continue; };
            let Some(&(start_tick, origin, velocity)) = launches.get(&photon) else { continue; };
            let Some(flight) = event.tick.checked_sub(start_tick) else { continue; };
            if flight == 0 || velocity.x * normal.x + velocity.y * normal.y != -SPEED_MM_PER_TICK
                || !inside(at, width, height) || origin.shifted(velocity, flight) != Some(at)
                || !seen_photons.insert(photon) { continue; }
            hits.push((photon, object, at, normal));
        }
        hits
    }

    /// Only independently received emission/contact pairs contribute to geometry.
    pub fn estimate_surfaces(&self) -> BTreeMap<u32, SurfaceEstimate> {
        let mut objects: BTreeMap<u32, SurfaceEstimate> = BTreeMap::new();
        for (_, object, point, normal) in self.valid_contacts() {
            let estimate = objects.entry(object).or_insert_with(|| SurfaceEstimate {
                object, min: point, max: point, faces: BTreeSet::new(), hit_samples: 0,
            });
            estimate.min.x = estimate.min.x.min(point.x);
            estimate.min.y = estimate.min.y.min(point.y);
            estimate.max.x = estimate.max.x.max(point.x);
            estimate.max.y = estimate.max.y.max(point.y);
            estimate.hit_samples += 1;
            estimate.faces.insert((normal.x, normal.y));
        }
        objects
    }

    /// A cautious extrapolation from the last validated observation, bounded by
    /// `max_extrapolation_ticks`. If contact is missing, projected motion is NOT
    /// confirmation of a clear path or the physical robot's position.
    pub fn project(&self, photon: u32, now_tick: u32,
                   max_extrapolation_ticks: u32) -> Option<PhotonPosition> {
        let (width, height, _) = self.epoch()?;
        let launch = self.messages.values().find_map(|event| match event.kind {
            Kind::Emitted { photon: id, at, velocity } if id == photon => Some((event.tick, at, velocity)),
            _ => None,
        })?;
        if !inside(launch.1, width, height) || now_tick < launch.0 { return None; }
        let contact = self.messages.values().filter_map(|event| match event.kind {
            Kind::Contact { photon: id, at, normal, .. } if id == photon && event.tick >= launch.0
                && launch.1.shifted(launch.2, event.tick - launch.0) == Some(at)
                && launch.2.x * normal.x + launch.2.y * normal.y == -SPEED_MM_PER_TICK
                && inside(at, width, height) => Some((event.tick, at, normal)),
            _ => None,
        }).filter(|&(tick, _, _)| tick <= now_tick).min_by_key(|&(tick, _, _)| tick);
        let (evidence_tick, origin, direction, reflected) = match contact {
            Some((tick, at, normal)) => {
                let dot = launch.2.x * normal.x + launch.2.y * normal.y;
                let velocity = Vec2::new(launch.2.x - 2 * dot * normal.x,
                                          launch.2.y - 2 * dot * normal.y);
                (tick, at, velocity, true)
            }
            None => (launch.0, launch.1, launch.2, false),
        };
        let age = now_tick - evidence_tick;
        if age > max_extrapolation_ticks { return None; }
        let position = origin.shifted(direction, age)?;
        Some(PhotonPosition { at: position, last_evidence_tick: evidence_tick, reflected })
    }
}
fn inside(at: Vec2, width: i32, height: i32) -> bool {
    at.x >= 0 && at.x <= width && at.y >= 0 && at.y <= height
}

#[cfg(test)]
#[path = "photons_tests.rs"]
mod tests;
