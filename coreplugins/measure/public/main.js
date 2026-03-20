const measureBuildVersion = '20260320-ui-tune2';

PluginsAPI.Map.willAddControls([
    	`measure/build/app.js?v=${measureBuildVersion}`,
    	`measure/build/app.css?v=${measureBuildVersion}`
	], function(args, App){
	new App(args.map);
});
