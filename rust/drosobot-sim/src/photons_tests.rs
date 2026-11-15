use super::*;

fn deliver(receiver: &mut EventReceiver, events: &[Event]) {
    for event in events { receiver.ingest(&event.encode()).expect("valid test packet"); }
}

#[test]
fn real_wire_roundtrip_for_all_three_kinds() {
    for message in CanonicalRoom::default().make_journal() {
        assert_eq!(Event::decode(&message.encode()), Ok(message));
    }
}

#[test]
fn decoder_rejects_malformed_and_unbounded_messages() {
    let base = CanonicalRoom::default().make_journal();
    let good = base[1].encode();
    for bad in [
        good[..19].to_vec(),
        { let mut b = good.clone(); b[4] = 2; b },
        { let mut b = good.clone(); b[5] = 99; b },
        { let mut b = good.clone(); b[6] = 1; b },
        { let mut b = good.clone(); b[12..16].copy_from_slice(&9999_u32.to_le_bytes()); b },
        { let mut b = good.clone(); b.extend_from_slice(&[0]); b },
        { let mut b = good.clone(); b[32..36].copy_from_slice(&7_i32.to_le_bytes()); b },
    ] {
        assert!(Event::decode(&bad).is_err(), "unexpected acceptance of {bad:?}");
    }
    let mut epoch = base[0].encode();
    epoch[36..40].copy_from_slice(&0_u32.to_le_bytes());
    assert_eq!(Event::decode(&epoch), Err("invalid_epoch"));
}

#[test]
fn out_of_order_and_duplicates_are_idempotent() {
    let journal = CanonicalRoom::default().make_journal();
    let mut rec = EventReceiver::new(journal[0].scene);
    // Contact arrives before its matching emission and before the epoch.
    deliver(&mut rec, &[journal[2].clone(), journal[0].clone()]);
    assert!(rec.estimate_surfaces().is_empty());
    deliver(&mut rec, &[journal[1].clone(), journal[2].clone()]);
    assert_eq!(rec.received(), 3);
    assert_eq!(rec.duplicates(), 1);
    assert_eq!(rec.estimate_surfaces().get(&1).unwrap().faces.len(), 1);
    let mut conflict = journal[2].clone();
    conflict.tick += 1;
    assert_eq!(rec.ingest(&conflict.encode()), Err("sequence_conflict"));
    let mut foreign = journal[3].clone();
    foreign.scene += 1;
    assert_eq!(rec.ingest(&foreign.encode()), Err("foreign_scene"));
}

#[test]
fn only_interactions_supported_by_emission_become_geometry() {
    let journal = CanonicalRoom::default().make_journal();
    let mut bad = journal[2].clone();
    if let Kind::Contact { ref mut at, .. } = bad.kind { at.x += 100; }
    let mut rec = EventReceiver::new(journal[0].scene);
    deliver(&mut rec, &[journal[0].clone(), journal[1].clone(), bad]);
    assert!(rec.estimate_surfaces().is_empty());
}

#[test]
fn complete_samples_recover_two_rectangle_bounds_without_shape_transfer() {
    let room = CanonicalRoom::default();
    let journal = room.make_journal();
    assert_eq!(journal.len(), 17);
    let mut rec = EventReceiver::new(journal[0].scene);
    deliver(&mut rec, &journal);
    let objects = rec.estimate_surfaces();
    assert_eq!(objects.len(), 2);
    assert_eq!(objects.values().map(|o| o.hit_samples).sum::<usize>(), 8);
    for (id, truth) in room.objects {
        let estimate = objects.get(&id).unwrap();
        assert!(estimate.complete_axis_aligned_rectangle());
        assert_eq!(estimate.min, truth.min);
        assert_eq!(estimate.max, truth.max);
    }
}

#[test]
fn missing_event_repair_recovers_both_objects() {
    let journal = CanonicalRoom::default().make_journal();
    let mut rec = EventReceiver::new(journal[0].scene);
    let delivered: Vec<_> = journal.iter().filter(|e| e.sequence % 7 != 0 || e.sequence == 0)
        .cloned().collect();
    deliver(&mut rec, &delivered);
    assert_eq!(rec.missing_through(16).unwrap(), vec![7, 14]);
    assert_eq!(rec.received(), 15);
    let before = rec.estimate_surfaces();
    assert_eq!(before.len(), 2);
    assert_eq!(before.values().filter(|x| x.complete_axis_aligned_rectangle()).count(), 0);
    for missing in rec.missing_through(16).unwrap() {
        rec.ingest(&journal[missing as usize].encode()).unwrap();
    }
    assert!(rec.missing_through(16).unwrap().is_empty());
    assert_eq!(rec.estimate_surfaces().values().filter(|x| x.complete_axis_aligned_rectangle()).count(), 2);
    assert!(rec.missing_through(MAX_EVENTS).is_err());
}

#[test]
fn moving_virtual_photon_reflects_then_expires() {
    let journal = CanonicalRoom::default().make_journal();
    let mut rec = EventReceiver::new(journal[0].scene);
    deliver(&mut rec, &journal[..3]);
    let hit_tick = journal[2].tick;
    assert_eq!(rec.project(1, hit_tick, 2).unwrap().at, Vec2::new(2000, 3000));
    assert_eq!(rec.project(1, hit_tick + 1, 2), Some(PhotonPosition {
        at: Vec2::new(1000, 3000), last_evidence_tick: hit_tick, reflected: true,
    }));
    assert!(rec.project(1, hit_tick + 3, 2).is_none());
    assert!(rec.project(1, journal[1].tick - 1, 2).is_none());
}

#[test]
fn logical_clock_rejects_large_uncertainty_or_future_timestamps() {
    let journal = CanonicalRoom::default().make_journal();
    let Kind::Epoch { origin_ms, tick_ms, .. } = &journal[0].kind else { unreachable!() };
    let (origin_ms, tick_ms) = (*origin_ms, *tick_ms);
    let clock = ClockAnchor { origin_ms, tick_ms };
    assert_eq!(clock.now_tick(origin_ms + 50 * 12, 0, 4, 8), Some(12));
    assert_eq!(clock.now_tick(origin_ms + 50 * 12 - 10, 10, 4, 8), Some(12));
    assert_eq!(clock.now_tick(origin_ms + 50 * 12, 0, 25, 30), None);
    assert_eq!(clock.now_tick(origin_ms + 50 * 12, 0, 10, 8), None);
    assert_eq!(clock.now_tick(origin_ms - 1, 0, 1, 8), None);
}

#[test]
fn event_log_replay_can_bootstrap_late_joiner() {
    let journal = CanonicalRoom::default().make_journal();
    let mut late = EventReceiver::new(journal[0].scene);
    assert!(late.estimate_surfaces().is_empty());
    // Sender exposes a trusted high-water mark and replays its log.
    for seq in late.missing_through(16).unwrap() {
        late.ingest(&journal[seq as usize].encode()).unwrap();
    }
    assert_eq!(late.estimate_surfaces().len(), 2);
    assert!(late.estimate_surfaces().values().all(SurfaceEstimate::complete_axis_aligned_rectangle));
}
