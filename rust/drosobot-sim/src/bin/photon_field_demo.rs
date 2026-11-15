//! Synthetic time-stamped virtual photons, delayed/reordered/dropped delivery,
//! event-log recovery and bounded extrapolation. Never connects to hardware.
use drosobot_sim::photons::{CanonicalRoom, Event, EventReceiver, SurfaceEstimate};
use std::collections::BTreeMap;

fn stream_with_jitter(events: &[Event], receiver: &mut EventReceiver) -> (usize, u64, u32) {
    let mut network: Vec<(u32, Vec<u8>)> = Vec::new();
    let mut dropped = 0;
    let mut bytes_on_wire: u64 = 0;
    for event in events {
        if event.sequence != 0 && event.sequence % 7 == 0 {
            dropped += 1;
            continue;
        }
        let packet = event.encode();
        let delay = 1 + (event.sequence * 11 % 8);
        bytes_on_wire += packet.len() as u64;
        network.push((event.tick + delay, packet.clone()));
        if event.sequence % 5 == 0 && event.sequence > 0 {
            // A transport duplicate to verify idempotency.
            bytes_on_wire += packet.len() as u64;
            network.push((event.tick + delay + 2, packet));
        }
    }
    network.sort_by(|left, right| left.0.cmp(&right.0)
        .then_with(|| right.1[12..16].cmp(&left.1[12..16])));
    for (_, raw) in network {
        receiver.ingest(&raw).expect("synthetic event must be accepted");
    }
    (dropped, bytes_on_wire, receiver.duplicates())
}

fn complete_count(estimated: &BTreeMap<u32, SurfaceEstimate>) -> usize {
    estimated.values().filter(|x| x.complete_axis_aligned_rectangle()).count()
}

fn main() {
    let sender = CanonicalRoom::default();
    let journal = sender.make_journal();
    let mut receiver = EventReceiver::new(journal[0].scene);
    let (lost, bytes_sent, duplicates) = stream_with_jitter(&journal, &mut receiver);
    let before = receiver.estimate_surfaces();
    let missing = receiver.missing_through(journal.last().unwrap().sequence).unwrap();
    println!("DrosoBot virtual photon lab (SYNTHETIC, not Wi-Fi RTT, not a physical robot)");
    println!("source_events={} original_event_bytes={} simulated_drops={} duplicate_packets={} delivered_bytes={}",
        journal.len(), journal.iter().map(|e| e.encode().len()).sum::<usize>(),
        lost, duplicates, bytes_sent);
    println!("before_replay: observed_surface_samples={} complete_objects={} missing_sequences={missing:?}",
        before.values().map(|x| x.hit_samples).sum::<usize>(), complete_count(&before));
    let mut replay_bytes = 0;
    for seq in missing {
        let raw = journal[seq as usize].encode();
        replay_bytes += raw.len();
        receiver.ingest(&raw).expect("correct replay");
    }
    let after = receiver.estimate_surfaces();
    let exact_objects = sender.objects.iter().filter(|(id, truth)| {
        after.get(id).is_some_and(|actual| actual.complete_axis_aligned_rectangle()
            && actual.min == truth.min && actual.max == truth.max)
    }).count();
    println!("after_replay: observed_surface_samples={} complete_objects={} exact_bounds={}/2 replay_bytes={replay_bytes}",
        after.values().map(|x| x.hit_samples).sum::<usize>(),
        complete_count(&after), exact_objects);
    for (id, object) in &after {
        println!("object={id} observed_faces={} min=({},{})mm max=({},{})mm",
            object.faces.len(),object.min.x,object.min.y,object.max.x,object.max.y);
    }
    assert_eq!(exact_objects, 2, "the synthetic scene must reconstruct exactly after replay");
    println!("sensor_source=declared_semantic_contact_events; movement_control=disabled; hardware_io=none");
}
