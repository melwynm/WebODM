import React from 'react';
import { shallow } from 'enzyme';
import EditPermissionsPanel from '../EditPermissionsPanel';


describe('<EditPermissionsPanel />', () => {
  it('maps the AirTwin role to view and acknowledgment permissions', () => {
    const wrapper = shallow(<EditPermissionsPanel projectId={1} />);
    const panel = wrapper.instance();

    expect(panel.extendedPermissions('airtwin')).toEqual(['view', 'acknowledge_airtwin_import']);
    expect(panel.simplifiedPermission(['view', 'acknowledge_airtwin_import'])).toBe('airtwin');
    expect(panel.permissionLabel('airtwin')).toBe('AirTwin integration');
  });
});
