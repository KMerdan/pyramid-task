import './side.js';
import { value } from './dep.js';
export { value as exposed } from './dep.js';
const one = require('./dep.js');
const two = import('./dep.js');
// import './fake.js';
const text = "require('./fake.js')";
const regexp = /import('fake')/;
import(variable);
