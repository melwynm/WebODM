import React from 'react';
import { shallow } from 'enzyme';
import AssetDownloadButtons from '../AssetDownloadButtons';

describe('<AssetDownloadButtons />', () => {
  it('renders without exploding', () => {
    const wrapper = shallow(<AssetDownloadButtons task={{project: 1, id: 1, available_assets: ["orthophoto.tif", "dsm.tif"]}} />);
    expect(wrapper.exists()).toBe(true);
  })

  it('shows gaussian splat downloads when the asset is available', () => {
    const wrapper = shallow(<AssetDownloadButtons task={{project: 1, id: 1, available_assets: ["gaussian_splat.ply"]}} />);
    expect(wrapper.text()).toContain('Gaussian Splat');
    expect(wrapper.find('a[href="/api/projects/1/tasks/1/download/gaussian_splat.ply"]').exists()).toBe(true);
  })
});
