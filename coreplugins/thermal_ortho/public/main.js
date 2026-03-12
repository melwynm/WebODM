PluginsAPI.Dashboard.addTaskActionButton([
    'thermal_ortho/build/ThermalPanel.js',
    'thermal_ortho/build/ThermalPanel.css'
], function(args, ThermalPanel){
    return React.createElement(ThermalPanel, { task: args.task });
});
