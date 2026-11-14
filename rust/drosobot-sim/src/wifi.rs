//! Room-level Wi-Fi fingerprint baseline, offline only. Not RF imaging, SLAM,
//! collision avoidance, or demonstrated ESP-Hi telemetry.
//!
//! Inputs must already be pseudonymized locally by a separately authorized
//! collector. Numeric IDs here are fictional fixtures, not home AP identifiers.
use std::collections::HashSet;

#[derive(Clone,Copy,Debug,Eq,PartialEq)]
pub enum ScanOrigin { Synthetic, EspHi, AuxiliaryReceiver }

#[derive(Clone,Copy,Debug,Eq,PartialEq)]
pub struct ApSignal { pub pseudonym:u64, pub rssi_dbm:i16 }

#[derive(Clone,Debug,Eq,PartialEq)]
pub struct Scan {
    pub tick:u64,
    pub origin:ScanOrigin,
    pub pseudonym_namespace:u32,
    pub signals:Vec<ApSignal>,
}

#[derive(Clone,Debug)]
pub struct Anchor {
    /// Opaque region index; real room names and home identifiers stay private.
    pub region:u16,
    pub pseudonym_namespace:u32,
    pub signals:Vec<ApSignal>,
}

#[derive(Clone,Copy,Debug,PartialEq)]
pub enum Estimate {
    Unknown(&'static str),
    Region { id:u16, heuristic_distance_db:f32, separation_db:f32 },
}

#[derive(Clone,Copy,Debug)]
pub struct Parameters {
    pub max_scan_age_ticks:u64,
    pub minimum_common_aps:usize,
    pub maximum_distance_db:f32,
    pub minimum_margin_db:f32,
}

impl Default for Parameters {
    fn default()->Self {Self {
        max_scan_age_ticks:2,minimum_common_aps:2,
        maximum_distance_db:15.,minimum_margin_db:5.,
    }}
}

fn valid(signals:&[ApSignal])->bool {
    if signals.len()<2 || signals.len()>128 {return false;}
    let mut seen=HashSet::new();
    signals.iter().all(|s|s.pseudonym!=0
        && (-100..=-20).contains(&s.rssi_dbm)
        && seen.insert(s.pseudonym))
}

fn distance(measured:&[ApSignal], reference:&[ApSignal],minimum_common:usize)->Option<f32> {
    let mut error=0f32;
    let mut matched=0usize;
    for m in measured {
        if let Some(a)=reference.iter().find(|a|a.pseudonym==m.pseudonym){
            matched+=1;
            error+=(m.rssi_dbm-a.rssi_dbm).abs() as f32;
        }
    }
    if matched<minimum_common {return None;}
    // Deliberately engineered missing-AP penalty; needs field calibration.
    let unmatched=measured.len()+reference.len()-2*matched;
    Some(error/matched as f32+12.*unmatched as f32/(matched+unmatched) as f32)
}

/// Conservative top-1 indoor-region baseline; not a probability or meter pose.
/// Unknown on ambiguous, stale, malformed, sparse or foreign-namespace scans.
pub fn locate(scan:&Scan, anchors:&[Anchor], now_tick:u64, parameters:Parameters)->Estimate {
    if now_tick<scan.tick || now_tick-scan.tick>parameters.max_scan_age_ticks {
        return Estimate::Unknown("scan_stale_or_future");
    }
    if !valid(&scan.signals) || scan.pseudonym_namespace==0 {
        return Estimate::Unknown("invalid_observation");
    }
    if anchors.is_empty() || !parameters.maximum_distance_db.is_finite() || parameters.maximum_distance_db<=0.
        || !parameters.minimum_margin_db.is_finite() || parameters.minimum_margin_db<0.
        || parameters.minimum_common_aps<2 {
        return Estimate::Unknown("invalid_reference_or_parameters");
    }
    let mut scores=Vec::new();
    for a in anchors {
        if a.pseudonym_namespace!=scan.pseudonym_namespace || !valid(&a.signals) {
            continue;
        }
        if let Some(score)=distance(&scan.signals,&a.signals,parameters.minimum_common_aps){
            scores.push((score,a.region));
        }
    }
    scores.sort_by(|a,b|a.0.total_cmp(&b.0).then(a.1.cmp(&b.1)));
    let Some(&(best,region))=scores.first() else {return Estimate::Unknown("insufficient_matching_access_points");};
    if best>parameters.maximum_distance_db {return Estimate::Unknown("fingerprint_too_distant");}
    let separation=scores.get(1).map(|(runner_up,_)|runner_up-best).unwrap_or(f32::INFINITY);
    if separation<parameters.minimum_margin_db {
        return Estimate::Unknown("ambiguous_region");
    }
    Estimate::Region{id:region,heuristic_distance_db:best,separation_db:separation}
}

/// Fictional fixture, not collected from an AP/router or a private household.
pub fn synthetic_reference()->(Vec<Anchor>, Vec<Scan>) {
    let ap=|id,rssi|ApSignal{pseudonym:id,rssi_dbm:rssi};
    let anchors=vec![
        Anchor{region:1,pseudonym_namespace:17,signals:vec![ap(11,-48),ap(22,-60),ap(33,-80)]},
        Anchor{region:2,pseudonym_namespace:17,signals:vec![ap(11,-78),ap(22,-49),ap(33,-55)]},
    ];
    let scans=vec![
        Scan{tick:1,origin:ScanOrigin::Synthetic,pseudonym_namespace:17,
            signals:vec![ap(11,-50),ap(22,-59),ap(33,-78)]},
        Scan{tick:2,origin:ScanOrigin::Synthetic,pseudonym_namespace:17,
            signals:vec![ap(11,-77),ap(22,-51),ap(33,-57)]},
        Scan{tick:3,origin:ScanOrigin::Synthetic,pseudonym_namespace:17,
            signals:vec![ap(11,-64),ap(22,-54),ap(33,-68)]},
    ];
    (anchors,scans)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn distinguishes_regions_and_rejects_ambiguity() {
        let (refs,scans)=synthetic_reference();
        assert!(matches!(locate(&scans[0],&refs,1,Parameters::default()),Estimate::Region{id:1,..}));
        assert!(matches!(locate(&scans[1],&refs,2,Parameters::default()),Estimate::Region{id:2,..}));
        assert!(matches!(locate(&scans[2],&refs,3,Parameters::default()),Estimate::Unknown(_)));
    }
    #[test]
    fn stale_future_and_wrong_namespace_abstain() {
        let (refs,mut scans)=synthetic_reference();
        assert_eq!(locate(&scans[0],&refs,7,Parameters::default()),Estimate::Unknown("scan_stale_or_future"));
        assert_eq!(locate(&scans[0],&refs,0,Parameters::default()),Estimate::Unknown("scan_stale_or_future"));
        scans[0].pseudonym_namespace=999;
        assert_eq!(locate(&scans[0],&refs,1,Parameters::default()),Estimate::Unknown("insufficient_matching_access_points"));
    }
    #[test]
    fn malformed_signal_and_sparse_input_abstain() {
        let (refs,mut scans)=synthetic_reference();
        scans[0].signals.push(scans[0].signals[0]);
        assert_eq!(locate(&scans[0],&refs,1,Parameters::default()),Estimate::Unknown("invalid_observation"));
        scans[0].signals.truncate(1);
        assert_eq!(locate(&scans[0],&refs,1,Parameters::default()),Estimate::Unknown("invalid_observation"));
        scans[0].signals[0].rssi_dbm=100;
        assert_eq!(locate(&scans[0],&refs,1,Parameters::default()),Estimate::Unknown("invalid_observation"));
    }
    #[test]
    fn dropout_rejected_if_too_few_shared_aps() {
        let (refs,mut scans)=synthetic_reference();
        scans[0].signals=vec![ApSignal{pseudonym:11,rssi_dbm:-49},ApSignal{pseudonym:44,rssi_dbm:-55}];
        assert_eq!(locate(&scans[0],&refs,1,Parameters::default()),Estimate::Unknown("insufficient_matching_access_points"));
    }
    #[test]
    fn no_meters_or_probabilities_are_claimed() {
        let (refs,scans)=synthetic_reference();
        if let Estimate::Region{heuristic_distance_db,..}=locate(&scans[0],&refs,1,Parameters::default()) {
            assert!(heuristic_distance_db>=0.);
        } else {panic!("region fixture unexpectedly unknown")}
    }
}
