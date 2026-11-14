//! Read-only, topology-faithful MaleCNS L3 compact operator.
//!
//! Derived from the public FlyDoom FlatBuffer decoding and `relax` update:
//! https://github.com/franklinbaldo/franklinbaldo.github.io/blob/main/public/fly-shader/sim.js
//! Fixed dynamics are **engineered**, not biologically proven; this module
//! does not implement learning, a physical robot driver, or motor decoding.
use std::fs;
use std::path::Path;

const MAX_BYTES: usize = 12_000_000;

fn u16le(src: &[u8], at: usize) -> Result<u16, String> {
    let bytes = src.get(at..at.checked_add(2).ok_or("u16 overflow")?).ok_or("u16 out of bounds")?;
    Ok(u16::from_le_bytes([bytes[0],bytes[1]]))
}
fn u32le(src: &[u8], at: usize) -> Result<u32, String> {
    let bytes = src.get(at..at.checked_add(4).ok_or("u32 overflow")?).ok_or("u32 out of bounds")?;
    Ok(u32::from_le_bytes([bytes[0],bytes[1],bytes[2],bytes[3]]))
}
fn f32le(src: &[u8], at: usize) -> Result<f32, String> { Ok(f32::from_bits(u32le(src,at)?)) }

fn flat_vector<'a>(src: &'a [u8], field: usize, width: usize) -> Result<&'a [u8], String> {
    let root = u32le(src,0)? as usize;
    let table_offset = u32le(src,root)? as usize;
    let vtable = root.checked_sub(table_offset).ok_or("invalid vtable offset")?;
    let vtable_len = u16le(src,vtable)? as usize;
    let slot = 4usize.checked_add(field.checked_mul(2).ok_or("field overflow")?).ok_or("field overflow")?;
    if slot + 2 > vtable_len { return Err("missing required FlatBuffer field".into()); }
    let field_rel = u16le(src,vtable+slot)? as usize;
    if field_rel==0 {return Err("required FlatBuffer field absent".into());}
    let position = root.checked_add(field_rel).ok_or("field address overflow")?;
    let vector = position.checked_add(u32le(src,position)? as usize).ok_or("vector start overflow")?;
    let length = u32le(src,vector)? as usize;
    let bytes = length.checked_mul(width).ok_or("vector byte count overflow")?;
    let start = vector.checked_add(4).ok_or("vector contents overflow")?;
    let end = start.checked_add(bytes).ok_or("vector end overflow")?;
    src.get(start..end).ok_or_else(||"truncated FlatBuffer vector".into())
}

#[derive(Clone, Copy, Debug)]
pub enum TargetMap { Original, Permuted }

/// Frozen sparse recurrent operator, with exactly the packed representation
/// of the FlyDoom artifact. The column-permutation is a **negative control**;
/// it is not a validated degree-preserving rewire or biological alternative.
#[derive(Clone, Debug)]
pub struct Brain {
    pub neurons:usize,
    pub edges:usize,
    offsets:Vec<usize>,
    scales:Vec<f32>,
    deltas:Vec<u16>,
    packed:Vec<u8>,
    lut:[f32;16],
    pub state:Vec<f32>,
    next:Vec<f32>,
    drive:Vec<f32>,
}
impl Brain {
    pub fn from_file(path:&Path)->Result<Self,String> {
        let meta=fs::metadata(path).map_err(|e|format!("cannot inspect artifact: {e}"))?;
        if meta.len() as usize>MAX_BYTES {return Err("brain artifact exceeds size limit".into());}
        let src=fs::read(path).map_err(|e|format!("cannot read brain artifact: {e}"))?;
        Self::parse(&src)
    }
    pub fn parse(src:&[u8])->Result<Self,String> {
        if src.len()>MAX_BYTES {return Err("brain artifact exceeds size limit".into());}
        let o=flat_vector(src,5,4)?;
        let scales_src=flat_vector(src,6,4)?;
        let d=flat_vector(src,7,2)?;
        let packed=flat_vector(src,8,1)?.to_vec();
        let lookup=flat_vector(src,9,4)?;
        if o.len()<8 || o.len()%4!=0 || scales_src.len()%4!=0 || d.len()%2!=0 || lookup.len()!=64 {
            return Err("invalid compact MaleCNS vector lengths".into());
        }
        let neurons=o.len()/4-1;
        if neurons==0 || neurons>500_000 || scales_src.len()/4!=neurons {return Err("invalid neuron counts".into());}
        let edges=d.len()/2;
        if (edges+1)/2!=packed.len() || edges==0 {return Err("invalid compressed edge counts".into());}
        let offsets:Vec<usize>=(0..neurons+1).map(|i|u32le(o,i*4).unwrap() as usize).collect();
        if offsets[0]!=0 || offsets[neurons]!=edges || offsets.windows(2).any(|a|a[0]>a[1]) {
            return Err("invalid CSR row pointers".into());
        }
        let scales:Vec<f32>=(0..neurons).map(|i|f32le(scales_src,i*4).unwrap()).collect();
        let deltas:Vec<u16>=(0..edges).map(|i|u16le(d,i*2).unwrap()).collect();
        let mut lut=[0f32;16];
        for (i,x) in lut.iter_mut().enumerate() { *x=f32le(lookup,i*4)?; }
        if scales.iter().chain(lut.iter()).any(|x|!x.is_finite()) {return Err("nonfinite weights/scales".into());}
        for row in 0..neurons {
            let mut col=0usize;
            for &delta in &deltas[offsets[row]..offsets[row+1]] {
                col=col.checked_add(delta as usize).ok_or("column overflow")?;
                if col>=neurons {return Err("edge target out of bounds".into());}
            }
        }
        Ok(Self{neurons,edges,offsets,scales,deltas,packed,lut,
            state:vec![0.;neurons],next:vec![0.;neurons],drive:vec![0.;neurons]})
    }
    pub fn step(&mut self, input:&[(usize,f32)], mapping:TargetMap)->Result<(),String> {
        for &(index,magnitude) in input {
            if index>=self.neurons || !magnitude.is_finite() || magnitude.abs()>1. {
                return Err("invalid drive index or strength".into());
            }
        }
        self.drive.fill(0.);
        for &(index,magnitude) in input {self.drive[index]=(self.drive[index]+magnitude).clamp(-1.,1.);}
        for row in 0..self.neurons {
            let mut column=0usize;
            let mut accumulator=0f32;
            for edge in self.offsets[row]..self.offsets[row+1] {
                column+=self.deltas[edge] as usize;
                // Bijective target-label permutation: preserves the global
                // multiset of column indegrees; does NOT preserve anatomy.
                let col=match mapping {TargetMap::Original=>column,
                    TargetMap::Permuted=>(column.wrapping_mul(3).wrapping_add(17))%self.neurons};
                let nibble=(self.packed[edge/2]>>(4*(edge%2)))&15;
                accumulator+=self.lut[nibble as usize]*self.state[col];
            }
            let result=0.65*self.state[row]+0.35*(accumulator*self.scales[row]*3.5+self.drive[row]).tanh();
            if !result.is_finite() {return Err("nonfinite brain activity".into());}
            self.next[row]=result;
        }
        std::mem::swap(&mut self.state,&mut self.next);
        Ok(())
    }
    pub fn average(&self,indices:&[usize])->Result<f32,String> {
        if indices.is_empty() || indices.iter().any(|&i|i>=self.neurons) {return Err("invalid readout indices".into());}
        Ok((indices.iter().map(|&i|self.state[i] as f64).sum::<f64>()/indices.len() as f64) as f32)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn refuses_non_flatbuffer_or_truncated() {
        assert!(Brain::parse(&[]).is_err());
        assert!(Brain::parse(&[0u8;32]).is_err());
        assert!(Brain::parse(&[1u8;100]).is_err());
    }
    #[test]
    fn load_rejects_missing_file() {
        assert!(Brain::from_file(Path::new("nonexistent-real-male-cns-artifact")).is_err());
    }
}
