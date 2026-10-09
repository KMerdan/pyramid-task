mod model;
use crate::model::{self, Thing as Alias};
#[path = "alt.rs"]
mod alternate;
const RAW: &str = r#"use fake::Thing; mod ghost;"#;
const DOC: &str = include_str!("../README.txt");
/* outer /* mod fake; */ use ghost::X; */
#[cfg(feature = "extra")]
mod optional;
include!(concat!("generated", ".rs"));
mod nested { mod child; use crate::model::Thing; }
