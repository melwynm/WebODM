const measureBuildVersion = '20260510-visible-map-measure';

PluginsAPI.Map.willAddControls([
    	`measure/build/app.js?v=${measureBuildVersion}`,
    	`measure/build/app.css?v=${measureBuildVersion}`
	], function(args, App){
	new App(args.map);
});
