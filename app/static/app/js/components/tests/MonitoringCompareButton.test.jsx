import React from 'react';
import { shallow } from 'enzyme';

import MonitoringCompareButton from '../MonitoringCompareButton';

describe('<MonitoringCompareButton />', () => {
  const timelineTasks = [
    {
      id: '1',
      name: 'Current',
      created_at: '2026-05-18T08:00:00Z',
      position: 1,
      readiness: {
        can_compare: true,
        assets: {
          orthophoto: true,
          dsm: true,
          dtm: true
        }
      }
    },
    {
      id: '2',
      name: 'Previous',
      created_at: '2026-05-17T08:00:00Z',
      position: 2,
      readiness: {
        can_compare: true,
        assets: {
          orthophoto: true,
          dsm: true,
          dtm: false
        }
      },
      pair_readiness: {
        can_compare: true,
        terrain_products: {
          dsm_delta: true,
          dtm_delta: false
        },
        cache: {
          ready: true,
          generated_at: '2026-05-18T10:00:00Z'
        },
        issues: []
      }
    }
  ];

  it('shows monitoring readiness before loading a comparison', () => {
    const wrapper = shallow(
      <MonitoringCompareButton
        task={{id: '1', project: 7, name: 'Current'}}
        mapType="orthophoto"
      />
    );

    wrapper.setState({
      open: true,
      timelineTasks,
      referenceTaskId: '1',
      compareTaskId: '2'
    });

    expect(wrapper.text()).toContain('Readiness');
    expect(wrapper.text()).toContain('Reference ready');
    expect(wrapper.text()).toContain('Compare ready');
    expect(wrapper.text()).toContain('DSM delta');
    expect(wrapper.text()).toContain('No DTM delta');
    expect(wrapper.text()).toContain('Cached');
  });
});
