import Widget from './widget.jsx';
export { Widget } from './widget.jsx';
const view = <div title="import './fake.js'">require('./fake.js')</div>;
const challenge = <Widget>{import(variable)}</Widget>;
