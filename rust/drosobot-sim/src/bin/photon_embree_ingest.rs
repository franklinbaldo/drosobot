//! Offline import of a DPH1 event journal from an independent Embree sender.
//! No network or motors. The oracle is visible to the *evaluator* only.
use drosobot_sim::photons::{CanonicalRoom, Event, EventReceiver, Kind, MAX_EVENTS};
use std::{env, fs, process};

fn import(data: &[u8]) -> Result<Vec<Event>, &'static str> {
    const MAX_JOURNAL_BYTES: usize = 44 * MAX_EVENTS as usize;
    if data.is_empty() || data.len() > MAX_JOURNAL_BYTES {
        return Err("journal_size_invalid");
    }
    let mut events = Vec::new();
    let mut pos = 0;
    while pos < data.len() {
        if events.len() >= MAX_EVENTS as usize || data.len() - pos < 20 {
            return Err("truncated_or_overlong_journal");
        }
        let size = match data[pos + 5] { 0 | 1 => 40, 2 => 44,
            _ => return Err("unknown_event_type") };
        if data.len() - pos < size { return Err("truncated_event"); }
        let event = Event::decode(&data[pos..pos + size])?;
        events.push(event);
        pos += size;
    }
    Ok(events)
}

fn evaluate(events: &[Event], bytes: usize) -> Result<(), &'static str> {
    let expected = CanonicalRoom::default().make_journal();
    if events.len() != expected.len() { return Err("event_count_mismatch"); }
    // A strict deterministic bridge test; no corpus overfitting claim implied.
    // Once this contract passes, separate test scenes / distributions are needed.
    if events != expected.as_slice() { return Err("journal_differs_from_independent_rust_oracle"); }
    let scene_id = expected[0].scene;
    let mut receiver = EventReceiver::new(scene_id);
    for event in events.iter().rev() { receiver.ingest(&event.encode())?; }
    let estimated = receiver.estimate_surfaces();
    let truth = CanonicalRoom::default();
    let correct = truth.objects.iter().filter(|(object, rect)| {
        estimated.get(object).is_some_and(|x| {
            x.complete_axis_aligned_rectangle() && x.min == rect.min && x.max == rect.max
        })
    }).count();
    let reflect_count = events.iter().filter(|x| matches!(x.kind, Kind::Contact { .. })).count();
    if correct != 2 || reflect_count != 8 { return Err("scene_reconstruction_mismatch"); }
    println!("source=embree_cpp_3d_intersections; wire=DPH1; hardware_control=none");
    println!("received_events={} bytes={} contact_events={} surfaces_reconstructed={}/2",
        events.len(), bytes, reflect_count, correct);
    println!("comparison=exact_journal_match_with_rust_synthetic_oracle; receiver_input=events_only");
    println!("clock=logical_ticks; distance_from_wifi_latency=not_inferred");
    Ok(())
}

fn main() {
    let args: Vec<String> = env::args().collect();
    if args.len() != 3 || args[1] != "--input" {
        eprintln!("usage: photon_embree_ingest --input PRIVATE_DPH1_JOURNAL");
        process::exit(2);
    }
    let result = fs::read(&args[2])
        .map_err(|_| "journal_file_cannot_be_read")
        .and_then(|data| import(&data).and_then(|events| evaluate(&events, data.len())));
    if let Err(error) = result {
        eprintln!("embree_bridge_error={error}");
        process::exit(1);
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn roundtrips_known_rust_journal() {
        let raw: Vec<u8> = CanonicalRoom::default().make_journal().iter()
            .flat_map(Event::encode).collect();
        let parsed = import(&raw).unwrap();
        assert_eq!(parsed.len(),17);
        assert_eq!(evaluate(&parsed,raw.len()),Ok(()));
    }
    #[test]
    fn rejects_truncation_padding_unknown_event_and_size() {
        let good: Vec<u8> = CanonicalRoom::default().make_journal().iter()
            .flat_map(Event::encode).collect();
        for mut raw in [good[..good.len()-1].to_vec(),
                        [good.clone(),vec![42]].concat(),
                        {let mut x=good.clone();x[5]=99;x},
                        vec![]] {
            assert!(import(&raw).is_err());
            raw.clear();
        }
    }
    #[test]
    fn rejects_wrong_scene_and_fake_geometry() {
        let mut journal = CanonicalRoom::default().make_journal();
        journal[2].tick += 1;
        let encoded: Vec<u8> = journal.iter().flat_map(Event::encode).collect();
        let decoded = import(&encoded).unwrap();
        assert_eq!(evaluate(&decoded,encoded.len()),Err("journal_differs_from_independent_rust_oracle"));
    }
}
